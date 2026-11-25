"""Opt-in diagnostics for tracing input, menus, and speech end to end."""

import logging
from pathlib import Path


LOGGER_NAME = "becker_bearings.debug"


def configure_debug_log(path):
    """Write detailed runtime diagnostics to *path* when explicitly enabled."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(threadName)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("debug log started path=%s", path)
    return logger


def debug(message, *args):
    logger = logging.getLogger(LOGGER_NAME)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(message, *args)
