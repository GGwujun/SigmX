"""Notify config persistence (JSON file).

System-level (not per-user): ``~/.vibe-trading/notify_config.json``.
Reads/writes are atomic (tmp + rename) and tolerate a missing file (defaults).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from src.notify.models import NotifyConfig

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path.home() / ".vibe-trading" / "notify_config.json"


def load_config() -> NotifyConfig:
    """Load notify config, returning defaults if missing/invalid."""
    try:
        if _CONFIG_PATH.is_file():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return NotifyConfig(**data)
    except Exception as exc:
        logger.warning("notify config load failed, using defaults: %s", exc)
    return NotifyConfig()


def save_config(cfg: NotifyConfig) -> None:
    """Atomically write the notify config."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(cfg.model_dump(), ensure_ascii=False, indent=2)
    # Atomic write: tmp file in same dir, then os.replace.
    fd, tmp = tempfile.mkstemp(dir=str(_CONFIG_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, _CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_platform_config(platform: str, cfg: NotifyConfig | None = None):
    """Return the PlatformConfig for a platform name, or None if unknown."""
    if cfg is None:
        cfg = load_config()
    platform = (platform or "").strip().lower()
    return getattr(cfg, platform, None)
