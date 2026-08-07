"""Entrypoint: wire config, GitLab client, mirror, scheduler and HTTP server together."""

import argparse
import logging
import sys

import uvicorn

from .api import create_app
from .backup import BackupRunner, BackupService, RepoMirror
from .config import AppConfig
from .config.settings import DEFAULT_CONFIG_FILE
from .gitlab_api import GitLabClient
from .logging_setup import setup_logging
from .scheduler import BackupScheduler

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GitLab groups mirror-backup service")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_FILE,
        help="Path to config.yml (env CONFIG_FILE works too, and takes the same effect)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single backup pass and exit - no HTTP server, no scheduler "
        "(useful for manual runs or if you'd rather drive this from external cron)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AppConfig.load(args.config)
    setup_logging(config.logging)

    client = GitLabClient(config.gitlab, config.gitlab_api_token)
    mirror = RepoMirror(config.gitlab, config.backup, config.gitlab_api_token)
    runner = BackupRunner(config, client, mirror)
    service = BackupService(runner)

    if args.once:
        service.run_once()
        results = service.last_results
        return 0 if all(r.success for r in results) else 1

    scheduler = None
    if config.schedule.enabled:
        scheduler = BackupScheduler(config.schedule, service.run_once)
        scheduler.start()
    else:
        logger.info("Internal scheduler disabled (schedule.enabled=false); trigger backups via POST /backup/run")

    app = create_app(service)
    try:
        # Blocks the main thread and serves as the container's foreground
        # process; the scheduler above keeps running in its own thread.
        uvicorn.run(app, host=config.server.host, port=config.server.port, log_config=None)
    finally:
        if scheduler:
            scheduler.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
