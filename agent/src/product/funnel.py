"""Privacy-minimal acquisition funnel for the individual Web product."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from src.product.store import ProductStore


FUNNEL_STAGES = (
    "landing_view",
    "search_submitted",
    "result_view",
    "pricing_view",
    "register_started",
    "register_completed",
    "login_completed",
    "download_clicked",
    "checkout_intent",
)
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class PersonalFunnelService:
    def __init__(self, store: ProductStore) -> None:
        self.store = store

    def record(self, session_id: str, event_name: str, occurred_at: str | None = None) -> bool:
        if not _SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid anonymous session")
        if event_name not in FUNNEL_STAGES:
            raise ValueError("unsupported funnel event")
        timestamp = occurred_at or datetime.now(timezone.utc).isoformat()
        event_day = timestamp[:10]
        with self.store.transaction() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO personal_funnel_events "
                "(id,anonymous_session_id,event_name,event_day,occurred_at) VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, session_id, event_name, event_day, timestamp),
            ).rowcount
        return inserted > 0

    def aggregate(self, start_at: str) -> dict[str, int]:
        rows = self.store._get_conn().execute(
            "SELECT event_name,COUNT(DISTINCT anonymous_session_id) sessions "
            "FROM personal_funnel_events WHERE occurred_at>=? GROUP BY event_name",
            (start_at,),
        ).fetchall()
        values = {stage: 0 for stage in FUNNEL_STAGES}
        values.update({row["event_name"]: int(row["sessions"]) for row in rows})
        return values
