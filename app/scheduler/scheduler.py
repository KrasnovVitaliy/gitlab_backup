"""Built-in scheduling, so the service doesn't depend on an external cron."""

import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import ScheduleConfig

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Runs a given job on the cadence described by ScheduleConfig.

    Runs in a background thread (`BackgroundScheduler`), so `start()` returns
    immediately - the caller is expected to keep the process alive itself
    (here, by handing off to uvicorn).
    """

    def __init__(self, schedule_config: ScheduleConfig, job: Callable[[], object]):
        self._config = schedule_config
        self._job = job
        self._scheduler = BackgroundScheduler(timezone=schedule_config.timezone)

    def start(self) -> None:
        if self._config.run_on_start:
            logger.info("run_on_start=true, scheduling an immediate backup pass")
            self._scheduler.add_job(self._safe_run, trigger="date", run_date=datetime.now(), id="gitlab_backup_initial")

        trigger = self._build_trigger()
        self._scheduler.add_job(
            self._safe_run,
            trigger,
            id="gitlab_backup",
            coalesce=True,  # if a run is missed (e.g. downtime), don't fire it multiple times back-to-back
            max_instances=1,  # never run two backup passes concurrently
        )
        self._scheduler.start()
        logger.info(
            "Scheduler started: type=%s (%s), timezone=%s",
            self._config.type,
            self._config.cron or self._config.interval_minutes,
            self._config.timezone,
        )

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _build_trigger(self):
        if self._config.type == "cron":
            if not self._config.cron:
                raise ValueError("schedule.cron must be set when schedule.type is 'cron'")
            return CronTrigger.from_crontab(self._config.cron, timezone=self._config.timezone)
        if self._config.type == "interval":
            if not self._config.interval_minutes:
                raise ValueError("schedule.interval_minutes must be set when schedule.type is 'interval'")
            return IntervalTrigger(minutes=self._config.interval_minutes)
        raise ValueError(f"Unknown schedule.type: '{self._config.type}' (expected 'cron' or 'interval')")

    def _safe_run(self) -> None:
        try:
            self._job()
        except Exception:
            logger.exception("Backup job raised an unhandled exception")
