from __future__ import annotations

import logging


DEFAULT_LOG_FORMAT = (
    "%(asctime)s %(levelname)s [%(name)s] %(message)s"
)


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        logging.basicConfig(level=numeric_level, format=DEFAULT_LOG_FORMAT)
        return

    root_logger.setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

