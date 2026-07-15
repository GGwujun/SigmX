from __future__ import annotations

import sys
from types import SimpleNamespace

from src.api import opportunity_routes


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_unmapped_global_event_cannot_create_stock_signal(monkeypatch) -> None:
    fake = SimpleNamespace(
        _CACHE_LOCK=_Lock(),
        _EVENTS_CACHE={
            "categories": [
                {"events": [{"title": "Global event", "prob_change_24h": 0.5}]}
            ]
        },
    )
    monkeypatch.setitem(sys.modules, "src.api.events_routes", fake)

    assert opportunity_routes._detect_event_catalyst(
        {"symbol": "600000.SH", "industry": "bank"}
    ) is None
