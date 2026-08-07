"""Orchestrates one full backup pass: discover projects, mirror them in parallel."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import AppConfig
from ..gitlab_api import GitLabClient, ProjectInfo
from .mirror import RepoMirror
from .models import BackupResult

logger = logging.getLogger(__name__)


class BackupRunner:
    """Ties config, discovery and mirroring together for a single run."""

    def __init__(self, config: AppConfig, client: GitLabClient, mirror: RepoMirror):
        self._config = config
        self._client = client
        self._mirror = mirror

    def run_once(self) -> list[BackupResult]:
        run_started = time.monotonic()
        logger.info("=== Backup run started ===")

        projects = self._client.discover_projects(
            group_refs=self._config.groups,
            include_subgroups=self._config.backup.include_subgroups,
            include_archived=self._config.backup.include_archived,
        )
        if not projects:
            logger.warning("No projects discovered, nothing to back up")
            return []

        results = self._mirror_all(projects)

        if self._config.backup.prune_removed:
            self._prune_missing(projects)

        self._log_summary(results, time.monotonic() - run_started)
        return results

    def _mirror_all(self, projects: list[ProjectInfo]) -> list[BackupResult]:
        workers = self._config.backup.parallel_workers
        logger.info("Backing up %d project(s) with %d parallel worker(s)", len(projects), workers)

        results: list[BackupResult] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._mirror.sync, p): p for p in projects}
            for future in as_completed(futures):
                project = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - defensive; sync() already catches its own errors
                    logger.exception("Unexpected error backing up %s", project.path_with_namespace)
                    result = BackupResult(
                        project=project,
                        success=False,
                        action="failed",
                        duration_seconds=0.0,
                        error=str(exc),
                    )
                results.append(result)
                self._log_result(result)
        return results

    def _prune_missing(self, current_projects: list[ProjectInfo]) -> None:
        current_paths = {p.path_with_namespace for p in current_projects}
        existing_paths = self._mirror.list_existing_mirrors()
        for stale_path in existing_paths - current_paths:
            self._mirror.remove(stale_path)

    @staticmethod
    def _log_result(result: BackupResult) -> None:
        if result.success:
            logger.info(
                "[OK] %s (%s, %.1fs)",
                result.project.path_with_namespace,
                result.action,
                result.duration_seconds,
            )
        else:
            logger.error("[FAIL] %s: %s", result.project.path_with_namespace, result.error)

    @staticmethod
    def _log_summary(results: list[BackupResult], total_seconds: float) -> None:
        ok = sum(1 for r in results if r.success)
        failed = len(results) - ok
        logger.info(
            "=== Backup run finished in %.1fs: %d succeeded, %d failed (of %d) ===",
            total_seconds,
            ok,
            failed,
            len(results),
        )
        if failed:
            for r in results:
                if not r.success:
                    logger.error("  - %s: %s", r.project.path_with_namespace, r.error)
