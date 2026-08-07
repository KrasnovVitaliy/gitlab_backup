"""Discovery of projects to back up, via the GitLab REST API."""

import logging

import gitlab
from pydantic import SecretStr

from ..config import GitLabConfig
from .models import ProjectInfo

logger = logging.getLogger(__name__)


class GitLabClient:
    """Thin wrapper around python-gitlab, scoped to what the backup service needs."""

    def __init__(self, config: GitLabConfig, api_token: SecretStr):
        self._gl = gitlab.Gitlab(
            config.url,
            private_token=api_token.get_secret_value(),
            ssl_verify=config.verify_ssl,
        )
        self._gl.auth()
        logger.info("Authenticated to %s as '%s'", config.url, self._gl.user.username)

    def discover_projects(
        self,
        group_refs,
        include_subgroups: bool,
        include_archived: bool,
    ) -> list[ProjectInfo]:
        """Resolve the configured group paths/ids into a deduplicated project list.

        Projects that appear in more than one configured group (e.g. a subgroup
        listed on its own as well as reachable through its parent) are only
        backed up once.
        """
        group_refs = list(group_refs)
        by_id: dict[int, ProjectInfo] = {}

        list_kwargs = {"all": True, "include_subgroups": include_subgroups}
        if not include_archived:
            list_kwargs["archived"] = False

        for ref in group_refs:
            try:
                group = self._gl.groups.get(ref)
            except gitlab.exceptions.GitlabGetError as exc:
                logger.error("Group '%s' not found or inaccessible: %s", ref, exc)
                continue

            projects = group.projects.list(**list_kwargs)
            logger.info(
                "Group '%s' (id=%s): %d project(s) found",
                group.full_path,
                group.id,
                len(projects),
            )

            for p in projects:
                if p.id in by_id:
                    continue
                by_id[p.id] = ProjectInfo(
                    id=p.id,
                    path_with_namespace=p.path_with_namespace,
                    http_url_to_repo=p.http_url_to_repo,
                    default_branch=getattr(p, "default_branch", None),
                    archived=p.archived,
                )

        logger.info(
            "Discovered %d unique project(s) across %d configured group(s)",
            len(by_id),
            len(group_refs),
        )
        return list(by_id.values())
