import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def _ensure_root_configured() -> None:
    root = logging.getLogger()
    if any(getattr(h, "_vibecheck_default", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler._vibecheck_default = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    if root.level == logging.WARNING:
        root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    _ensure_root_configured()
    return logging.getLogger(name)
