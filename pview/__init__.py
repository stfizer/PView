"""P view - a Windows 11 style image viewer inspired by BandiView."""

import logging
import logging.handlers
import os

APP_NAME = "P view"
APP_VERSION = "1.0.0"
ORG_NAME = "PView"

_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger
    try:
        from .settings import app_data_dir
        log_dir = app_data_dir()
    except Exception:
        log_dir = os.path.join(os.environ.get("TEMP", "."), "PView")
        os.makedirs(log_dir, exist_ok=True)
    lp = os.path.join(log_dir, "pview.log")
    logger = logging.getLogger("pview")
    logger.setLevel(logging.DEBUG)
    try:
        h = logging.handlers.RotatingFileHandler(lp, maxBytes=200_000,
                                                 backupCount=1, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(h)
    except Exception:
        pass
    _logger = logger
    return logger


def log_exception(msg: str, exc: BaseException | None = None):
    try:
        get_logger().exception(msg, exc_info=exc is not None)
    except Exception:
        pass
