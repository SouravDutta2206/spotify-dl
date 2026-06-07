"""Session logging for spotify-dl.

Each invocation creates two timestamped files in ``~/.spotify-dl/logs/``:

* ``log-<timestamp>.log``    — full detailed session log
* ``failed-<timestamp>.log`` — failed tracks only (concise)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".spotify-dl" / "logs"

_FULL_FMT = "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s"
_FAILED_FMT = "[%(asctime)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class SessionLog:
    log_path: Path
    failed_path: Path


def setup_session_logging() -> SessionLog:
    """Initialise file-based logging for the current session.

    Must be called exactly once, early in ``main()``.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    log_path = LOG_DIR / f"log-{stamp}.log"
    failed_path = LOG_DIR / f"failed-{stamp}.log"

    # ── Root logger for the spotify_dl namespace ──────────────────────────
    root = logging.getLogger("spotify_dl")
    root.setLevel(logging.DEBUG)

    full_handler = logging.FileHandler(log_path, encoding="utf-8")
    full_handler.setLevel(logging.DEBUG)
    full_handler.setFormatter(logging.Formatter(_FULL_FMT, datefmt=_DATE_FMT))
    root.addHandler(full_handler)

    # ── Dedicated failed-tracks logger ────────────────────────────────────
    failed = logging.getLogger("spotify_dl.failed")
    failed.setLevel(logging.DEBUG)
    failed.propagate = False  # don't duplicate into the full log

    failed_handler = logging.FileHandler(failed_path, encoding="utf-8")
    failed_handler.setLevel(logging.DEBUG)
    failed_handler.setFormatter(logging.Formatter(_FAILED_FMT, datefmt=_DATE_FMT))
    failed.addHandler(failed_handler)

    return SessionLog(log_path, failed_path)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``spotify_dl`` namespace."""
    return logging.getLogger(f"spotify_dl.{name}")
