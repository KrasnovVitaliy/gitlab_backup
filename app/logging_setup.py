"""Central logging configuration, using the standard library logging module."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import LoggingConfig

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(config: LoggingConfig) -> None:
    root = logging.getLogger()
    root.setLevel(config.level)
    root.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if config.file:
        log_path = Path(config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=14, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
