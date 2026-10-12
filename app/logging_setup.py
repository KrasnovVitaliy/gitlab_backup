"""Central logging configuration, using the standard library logging module."""

import logging
import sys

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
