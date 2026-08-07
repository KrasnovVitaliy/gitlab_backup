"""Cloning/updating a single project as a bare mirror repository on disk."""

import logging
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr

from ..config import BackupConfig, GitLabConfig
from ..gitlab_api import ProjectInfo
from .models import BackupResult

logger = logging.getLogger(__name__)


class RepoMirror:
    """Knows how to sync one GitLab project to `<root_dir>/<namespace>/<repo>.git`.

    Clones/fetches over HTTPS with the same token used for the API - no
    separate SSH key/known_hosts to manage.
    """

    def __init__(self, gitlab_config: GitLabConfig, backup_config: BackupConfig, api_token: SecretStr):
        self._gitlab_config = gitlab_config
        self._backup_config = backup_config
        self._api_token = api_token

    def sync(self, project: ProjectInfo) -> BackupResult:
        """Clone the project if it's not on disk yet, otherwise fetch updates.

        A `git clone --mirror` pulls every branch/tag/ref exactly as GitLab has
        it. On subsequent runs we just fetch, which is far cheaper than a full
        re-clone once there are hundreds of repos.
        """
        started = time.monotonic()
        dest = self._dest_path(project)
        attempts = self._backup_config.retries + 1
        last_error: str | None = None
        clone_url = self._authenticated_url(project.http_url_to_repo)

        for attempt in range(1, attempts + 1):
            try:
                if dest.exists():
                    action = "updated"
                    # Refresh the remote URL every run in case the token was
                    # rotated since the initial clone.
                    self._run_git(["remote", "set-url", "origin", clone_url], cwd=dest)
                    result = self._run_git(["fetch", "--prune", "origin"], cwd=dest)
                else:
                    action = "cloned"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    result = self._run_git(["clone", "--mirror", clone_url, str(dest)])

                if result.returncode != 0:
                    raise RuntimeError(self._redact(result.stderr.strip() or result.stdout.strip()))

                return BackupResult(
                    project=project,
                    success=True,
                    action=action,
                    duration_seconds=time.monotonic() - started,
                )
            except subprocess.TimeoutExpired:
                last_error = f"timed out after {self._backup_config.clone_timeout}s"
            except Exception as exc:  # noqa: BLE001 - any failure here should be retried and reported
                last_error = self._redact(str(exc))

            logger.warning(
                "[%s] attempt %d/%d failed: %s",
                project.path_with_namespace,
                attempt,
                attempts,
                last_error,
            )

        return BackupResult(
            project=project,
            success=False,
            action="failed",
            duration_seconds=time.monotonic() - started,
            error=last_error,
        )

    def list_existing_mirrors(self) -> set[str]:
        """Return the set of project paths currently backed up on disk."""
        root = Path(self._backup_config.root_dir)
        if not root.exists():
            return set()
        return {str(p.relative_to(root)).removesuffix(".git") for p in root.rglob("*.git") if p.is_dir()}

    def remove(self, project_path: str) -> None:
        dest = Path(self._backup_config.root_dir) / f"{project_path}.git"
        if dest.exists():
            logger.warning("Removing mirror of project no longer present in GitLab: %s", dest)
            shutil.rmtree(dest)

    def _dest_path(self, project: ProjectInfo) -> Path:
        return Path(self._backup_config.root_dir) / f"{project.path_with_namespace}.git"

    def _authenticated_url(self, http_url: str) -> str:
        """Embed the access token as HTTP basic auth in the clone URL.

        GitLab accepts any non-empty username with a Personal/Project/Group
        Access Token as the password over HTTPS.
        """
        parts = urlsplit(http_url)
        netloc = f"oauth2:{self._api_token.get_secret_value()}@{parts.hostname}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def _redact(self, text: str) -> str:
        """Strip the token out of git output before it's logged or raised."""
        return text.replace(self._api_token.get_secret_value(), "***")

    def _run_git(self, args, cwd: Path | None = None) -> subprocess.CompletedProcess:
        git_args = ["git"]
        if not self._gitlab_config.verify_ssl:
            git_args += ["-c", "http.sslVerify=false"]
        git_args += args
        return subprocess.run(
            git_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=self._backup_config.clone_timeout,
        )
