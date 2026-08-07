"""Coordinates backup runs triggered from multiple places (scheduler, HTTP API)."""

import logging
import threading
from datetime import UTC, datetime

from .models import BackupResult
from .runner import BackupRunner

logger = logging.getLogger(__name__)


class BackupService:
    """Wraps BackupRunner with a run lock and last-run bookkeeping.

    The scheduler and the HTTP `/backup/run` endpoint both call `run_once()`
    on the same instance, so a manual trigger can never overlap with a
    scheduled run (or another manual trigger) - the second caller is skipped
    instead of running two mirror passes at once.
    """

    def __init__(self, runner: BackupRunner):
        self._runner = runner
        self._lock = threading.Lock()
        self._running = False
        self._last_started_at: datetime | None = None
        self._last_finished_at: datetime | None = None
        self._last_results: list[BackupResult] = []

    def run_once(self) -> bool:
        """Run a backup pass unless one is already in progress.

        Returns False (without doing anything) if a run was already active.
        """
        if not self._lock.acquire(blocking=False):
            logger.warning("Backup run requested while another run is in progress, skipping")
            return False
        try:
            self._running = True
            self._last_started_at = datetime.now(UTC)
            self._last_results = self._runner.run_once()
            return True
        finally:
            self._last_finished_at = datetime.now(UTC)
            self._running = False
            self._lock.release()

    @property
    def last_results(self) -> list[BackupResult]:
        return self._last_results

    def status(self) -> dict:
        results = self._last_results
        succeeded = sum(1 for r in results if r.success)
        return {
            "running": self._running,
            "last_started_at": _isoformat(self._last_started_at),
            "last_finished_at": _isoformat(self._last_finished_at),
            "last_run": None
            if not results
            else {
                "total": len(results),
                "succeeded": succeeded,
                "failed": len(results) - succeeded,
                "failures": [
                    {"project": r.project.path_with_namespace, "error": r.error} for r in results if not r.success
                ],
            },
        }


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
