from __future__ import annotations

import pytest

from src.product.funnel import FUNNEL_STAGES, PersonalFunnelService
from src.product.store import ProductStore


def test_funnel_accepts_only_fixed_events_and_anonymous_ids(tmp_path):
    service = PersonalFunnelService(ProductStore(tmp_path / "product.db"))
    assert service.record("browser_session_1234", "landing_view", "2026-08-16T00:00:00+00:00") is True
    assert service.record("browser_session_1234", "landing_view", "2026-08-16T00:01:00+00:00") is False
    assert service.record("browser_session_1234", "landing_view", "2026-08-17T00:01:00+00:00") is True
    with pytest.raises(ValueError):
        service.record("short", "landing_view")
    with pytest.raises(ValueError):
        service.record("browser_session_1234", "enterprise_lead")


def test_funnel_aggregates_unique_personal_browser_sessions(tmp_path):
    service = PersonalFunnelService(ProductStore(tmp_path / "product.db"))
    service.record("browser_session_1234", "landing_view", "2026-08-16T00:00:00+00:00")
    service.record("browser_session_1234", "search_submitted", "2026-08-16T00:01:00+00:00")
    service.record("browser_session_5678", "landing_view", "2026-08-16T00:02:00+00:00")
    aggregate = service.aggregate("2026-08-16")
    assert aggregate["landing_view"] == 2
    assert aggregate["search_submitted"] == 1
    assert set(aggregate) == set(FUNNEL_STAGES)
