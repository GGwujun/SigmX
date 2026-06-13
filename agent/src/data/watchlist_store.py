"""Position watchlist persistence (~/.vibe-trading/watchlist.json).

Simple JSON-file store for the user's A-share watchlist. One file per
machine — no multi-device sync.

Atomic write via temp-file + rename (crash-safe on all platforms).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    root = Path.home() / ".vibe-trading"
    root.mkdir(parents=True, exist_ok=True)
    return root / "watchlist.json"


def load_watchlist() -> list[dict[str, Any]]:
    """Return the current watchlist, or an empty list if the file is absent."""
    path = _store_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Validate items have at least a symbol field
            return [item for item in data if isinstance(item, dict) and "symbol" in item]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_watchlist(items: list[dict[str, Any]]) -> None:
    """Atomically write the full watchlist to disk.

    Uses a temp file + rename so a crash mid-write cannot corrupt the
    existing file.
    """
    path = _store_path()
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    # Write to temp file, then atomically rename (crash-safe on the same fs)
    tmp.write_text(payload, encoding="utf-8")
    # On Windows, pathlib.write_text() closes the handle before returning,
    # so the rename below is safe. On POSIX we don't need fsync for a
    # single-file rename — if the rename completes, the data is there.
    tmp.replace(path)


def remove_from_watchlist(symbol: str) -> bool:
    """Remove a single symbol from the watchlist. Returns True if removed."""
    items = load_watchlist()
    before = len(items)
    items = [item for item in items if item.get("symbol") != symbol]
    if len(items) < before:
        save_watchlist(items)
        return True
    return False
