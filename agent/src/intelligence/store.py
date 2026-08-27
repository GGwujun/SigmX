from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.intelligence.models import (
    ArticleSearchResult,
    ArticleWriteResult,
    EventEvidence,
    EventEvidenceView,
    EventSearchResult,
    EventView,
    GlobalEvent,
    NormalizedArticle,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS intelligence_articles (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, upstream_id TEXT NOT NULL,
 title TEXT NOT NULL, url TEXT NOT NULL, source_name TEXT NOT NULL,
 source_tier TEXT NOT NULL, published_at TEXT NOT NULL, fetched_at TEXT NOT NULL,
 content_type TEXT NOT NULL, summary TEXT NOT NULL, market TEXT NOT NULL,
 language TEXT NOT NULL, region TEXT NOT NULL, content_policy TEXT NOT NULL,
 metadata_json TEXT NOT NULL, UNIQUE(source_id, upstream_id)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_articles_published ON intelligence_articles(published_at DESC);
CREATE TABLE IF NOT EXISTS global_events (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL,
 event_type TEXT NOT NULL, status TEXT NOT NULL, first_seen_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, importance REAL NOT NULL, confidence REAL NOT NULL,
 region TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS global_event_evidence (
 event_id TEXT NOT NULL, article_id TEXT NOT NULL, is_key INTEGER NOT NULL,
 strength REAL NOT NULL, PRIMARY KEY(event_id, article_id),
 FOREIGN KEY(event_id) REFERENCES global_events(id),
 FOREIGN KEY(article_id) REFERENCES intelligence_articles(id)
);
CREATE TABLE IF NOT EXISTS global_event_versions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class IntelligenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.RLock()

    @staticmethod
    def _article_id(item: NormalizedArticle) -> str:
        key = f"{item.source_id}:{item.upstream_id}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()[:32]

    def upsert_articles(self, articles: list[NormalizedArticle]) -> ArticleWriteResult:
        inserted = updated = 0
        stored: list[NormalizedArticle] = []
        with self._lock, self._conn:
            for item in articles:
                item.id = item.id or self._article_id(item)
                exists = self._conn.execute(
                    "SELECT 1 FROM intelligence_articles WHERE source_id=? AND upstream_id=?",
                    (item.source_id, item.upstream_id),
                ).fetchone()
                self._conn.execute(
                    """INSERT INTO intelligence_articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_id,upstream_id) DO UPDATE SET
                    title=excluded.title,url=excluded.url,source_name=excluded.source_name,
                    source_tier=excluded.source_tier,published_at=excluded.published_at,
                    fetched_at=excluded.fetched_at,content_type=excluded.content_type,
                    summary=excluded.summary,market=excluded.market,language=excluded.language,
                    region=excluded.region,content_policy=excluded.content_policy,
                    metadata_json=excluded.metadata_json""",
                    (item.id, item.source_id, item.upstream_id, item.title, item.url,
                     item.source_name, item.source_tier, item.published_at.isoformat(),
                     item.fetched_at.isoformat(), item.content_type, item.summary, item.market,
                     item.language, item.region, item.content_policy,
                     json.dumps(item.metadata, ensure_ascii=False, default=str)),
                )
                inserted += not bool(exists)
                updated += bool(exists)
                stored.append(item)
        return ArticleWriteResult(inserted, updated, stored)

    def search_articles(self, *, query: str = "", limit: int = 30, offset: int = 0) -> ArticleSearchResult:
        where = "WHERE title LIKE ? OR summary LIKE ?" if query else ""
        args: tuple[object, ...] = (f"%{query}%", f"%{query}%") if query else ()
        with self._lock:
            total = self._conn.execute(f"SELECT COUNT(*) FROM intelligence_articles {where}", args).fetchone()[0]
            rows = self._conn.execute(
                f"SELECT * FROM intelligence_articles {where} ORDER BY published_at DESC LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
        return ArticleSearchResult([self._row_article(row) for row in rows], total)

    def upsert_event(self, event: GlobalEvent, evidence: list[EventEvidence]) -> GlobalEvent:
        if not evidence:
            raise ValueError("global event requires traceable evidence")
        event.id = event.id or uuid.uuid5(uuid.NAMESPACE_URL, f"sigmx:event:{event.title}:{event.first_seen_at.date()}").hex
        payload = asdict(event)
        payload["first_seen_at"] = event.first_seen_at.isoformat()
        payload["updated_at"] = event.updated_at.isoformat()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO global_events VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,summary=excluded.summary,
                event_type=excluded.event_type,status=excluded.status,updated_at=excluded.updated_at,
                importance=excluded.importance,confidence=excluded.confidence,region=excluded.region,
                metadata_json=excluded.metadata_json""",
                (event.id, event.title, event.summary, event.event_type, event.status,
                 event.first_seen_at.isoformat(), event.updated_at.isoformat(), event.importance,
                 event.confidence, event.region, json.dumps(event.metadata, ensure_ascii=False)),
            )
            for item in evidence:
                self._conn.execute(
                    "INSERT OR REPLACE INTO global_event_evidence VALUES (?,?,?,?)",
                    (event.id, item.article_id, int(item.is_key), item.strength),
                )
            self._conn.execute(
                "INSERT INTO global_event_versions(event_id,payload_json,created_at) VALUES (?,?,?)",
                (event.id, json.dumps(payload, ensure_ascii=False), event.updated_at.isoformat()),
            )
        return event

    def get_event(self, event_id: str) -> EventView:
        with self._lock:
            row = self._conn.execute("SELECT * FROM global_events WHERE id=?", (event_id,)).fetchone()
            if row is None:
                raise KeyError(event_id)
            evidence_rows = self._conn.execute(
                """SELECT a.*, e.is_key, e.strength FROM global_event_evidence e
                JOIN intelligence_articles a ON a.id=e.article_id WHERE e.event_id=?""",
                (event_id,),
            ).fetchall()
        return EventView(self._row_event(row), [EventEvidenceView(self._row_article(r), bool(r["is_key"]), r["strength"]) for r in evidence_rows])

    def list_event_versions(self, event_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM global_event_versions WHERE event_id=? ORDER BY id", (event_id,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_events(
        self, *, event_type: str = "", status: str = "", limit: int = 30, offset: int = 0
    ) -> EventSearchResult:
        clauses: list[str] = []
        args: list[object] = []
        if event_type:
            clauses.append("event_type=?")
            args.append(event_type)
        if status:
            clauses.append("status=?")
            args.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            total = self._conn.execute(f"SELECT COUNT(*) FROM global_events {where}", args).fetchone()[0]
            rows = self._conn.execute(
                f"SELECT id FROM global_events {where} ORDER BY importance DESC, updated_at DESC LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
        return EventSearchResult([self.get_event(row["id"]) for row in rows], total)

    @staticmethod
    def _row_article(row: sqlite3.Row) -> NormalizedArticle:
        return NormalizedArticle(
            id=row["id"], upstream_id=row["upstream_id"], title=row["title"], url=row["url"],
            source_id=row["source_id"], source_name=row["source_name"], source_tier=row["source_tier"],
            published_at=datetime.fromisoformat(row["published_at"]), fetched_at=datetime.fromisoformat(row["fetched_at"]),
            content_type=row["content_type"], summary=row["summary"], market=row["market"],
            language=row["language"], region=row["region"], content_policy=row["content_policy"],
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _row_event(row: sqlite3.Row) -> GlobalEvent:
        return GlobalEvent(
            id=row["id"], title=row["title"], summary=row["summary"], event_type=row["event_type"],
            status=row["status"], first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]), importance=row["importance"],
            confidence=row["confidence"], region=row["region"], metadata=json.loads(row["metadata_json"]),
        )
