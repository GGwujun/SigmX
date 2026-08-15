"""Personal cloud research assets shared by Web and connected Desktop."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.product.store import ProductStore


class ReportNotFound(Exception):
    pass


class ReportRevoked(Exception):
    pass


@dataclass(frozen=True)
class SavedQuery:
    id: str
    user_id: str
    query: str
    result_summary: dict
    created_at: str


@dataclass(frozen=True)
class CloudWatchlistItem:
    user_id: str
    symbol: str
    name: str
    created_at: str


@dataclass(frozen=True)
class ReportSnapshot:
    id: str
    user_id: str
    slug: str
    title: str
    summary: str
    created_at: str
    revoked_at: str | None


class CloudResearchService:
    def __init__(self, store: ProductStore) -> None:
        self.store = store

    def save_query(self, user_id: str, query: str, result_summary: dict) -> SavedQuery:
        query = query.strip()
        if not query:
            raise ValueError("query is required")
        item = SavedQuery(
            id=str(uuid.uuid4()),
            user_id=user_id,
            query=query,
            result_summary=dict(result_summary),
            created_at=self._now(),
        )
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO saved_queries (id,user_id,query,result_summary_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (item.id, item.user_id, item.query, json.dumps(item.result_summary, ensure_ascii=False), item.created_at),
            )
        return item

    def list_saved_queries(self, user_id: str) -> list[SavedQuery]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM saved_queries WHERE user_id=? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        return [
            SavedQuery(row["id"], row["user_id"], row["query"], json.loads(row["result_summary_json"]), row["created_at"])
            for row in rows
        ]

    def add_watchlist(self, user_id: str, symbol: str, name: str) -> CloudWatchlistItem:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        now = self._now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO cloud_watchlist (user_id,symbol,name,created_at) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id,symbol) DO UPDATE SET name=excluded.name",
                (user_id, symbol, name.strip(), now),
            )
            row = conn.execute(
                "SELECT * FROM cloud_watchlist WHERE user_id=? AND symbol=?", (user_id, symbol)
            ).fetchone()
        return CloudWatchlistItem(row["user_id"], row["symbol"], row["name"], row["created_at"])

    def list_watchlist(self, user_id: str) -> list[CloudWatchlistItem]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM cloud_watchlist WHERE user_id=? ORDER BY created_at DESC, symbol",
            (user_id,),
        ).fetchall()
        return [CloudWatchlistItem(row["user_id"], row["symbol"], row["name"], row["created_at"]) for row in rows]

    def remove_watchlist(self, user_id: str, symbol: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM cloud_watchlist WHERE user_id=? AND symbol=?",
                (user_id, symbol.strip().upper()),
            )
        return cursor.rowcount > 0

    def publish_report(self, user_id: str, title: str, summary: str) -> ReportSnapshot:
        title, summary = title.strip(), summary.strip()
        if not title or not summary:
            raise ValueError("title and summary are required")
        item = ReportSnapshot(
            id=str(uuid.uuid4()), user_id=user_id, slug=uuid.uuid4().hex,
            title=title, summary=summary, created_at=self._now(), revoked_at=None,
        )
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO report_snapshots (id,user_id,slug,title,summary,created_at,revoked_at) "
                "VALUES (?,?,?,?,?,?,NULL)",
                (item.id, item.user_id, item.slug, item.title, item.summary, item.created_at),
            )
        return item

    def list_reports(self, user_id: str) -> list[ReportSnapshot]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM report_snapshots WHERE user_id=? ORDER BY created_at DESC, id DESC", (user_id,)
        ).fetchall()
        return [self._report(row) for row in rows]

    def get_public_report(self, slug: str) -> ReportSnapshot:
        row = self.store._get_conn().execute(
            "SELECT * FROM report_snapshots WHERE slug=?", (slug,)
        ).fetchone()
        if row is None:
            raise ReportNotFound(slug)
        if row["revoked_at"] is not None:
            raise ReportRevoked(slug)
        return self._report(row)

    def revoke_report(self, user_id: str, report_id: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "UPDATE report_snapshots SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                (self._now(), report_id, user_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _report(row) -> ReportSnapshot:
        return ReportSnapshot(row["id"], row["user_id"], row["slug"], row["title"], row["summary"], row["created_at"], row["revoked_at"])

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
