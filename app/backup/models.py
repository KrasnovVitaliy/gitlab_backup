"""Data shapes describing the outcome of a backup operation."""

from dataclasses import dataclass

from ..gitlab_api import ProjectInfo


@dataclass
class BackupResult:
    """Outcome of mirroring a single project."""

    project: ProjectInfo
    success: bool
    action: str  # "cloned" | "updated" | "failed"
    duration_seconds: float
    error: str | None = None
