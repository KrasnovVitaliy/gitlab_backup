"""Data shapes describing objects fetched from the GitLab API."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectInfo:
    """A GitLab project as discovered through the API, trimmed to what we need."""

    id: int
    path_with_namespace: str
    http_url_to_repo: str
    default_branch: str | None
    archived: bool
