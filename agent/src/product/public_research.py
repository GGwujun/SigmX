"""Limited, anonymous Web research reads over the local public market store."""

from __future__ import annotations

from dataclasses import dataclass

from src.data.market_store import MarketStore


class InstrumentNotFound(Exception):
    pass


@dataclass(frozen=True)
class PublicSearchItem:
    code: str
    name: str
    industry: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    as_of: str | None


@dataclass(frozen=True)
class PublicSearchResult:
    query: str
    interpretation: list[str]
    items: list[PublicSearchItem]
    source: str = "local_market_store"
    is_delayed: bool = True


@dataclass(frozen=True)
class PublicStockSummary:
    code: str
    name: str
    industry: str | None
    market: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    as_of: str | None
    source: str = "local_market_store"
    is_delayed: bool = True


@dataclass(frozen=True)
class PublicFundSummary:
    code: str
    name: str
    fund_type: str | None
    close: float | None
    change_percent: float | None
    as_of: str | None
    source: str = "local_market_store"
    is_delayed: bool = True


class PublicResearchService:
    """Read-only facade that deliberately exposes fewer fields than Data Hub."""

    def __init__(self, store: MarketStore | None = None) -> None:
        self.store = store or MarketStore()

    def search(self, query: str, limit: int = 10) -> PublicSearchResult:
        query = query.strip()
        if not query:
            raise ValueError("query is required")
        limit = min(max(int(limit), 1), 10)
        interpretations: list[str] = []
        clauses = ["s.is_active=1"]
        params: list[object] = []
        if "低估值" in query:
            clauses.append("b.pe_ttm > 0 AND b.pe_ttm <= 20")
            interpretations.append("市盈率 0-20")
        if "高股息" in query:
            clauses.append("b.dv_ttm >= 3")
            interpretations.append("股息率 ≥ 3%")
        small_cap = "小市值" in query
        if small_cap:
            interpretations.append("按总市值升序")

        text = query
        for marker in ("低估值", "高股息", "小市值"):
            text = text.replace(marker, " ")
        terms = [term for term in text.split() if term]
        for term in terms:
            clauses.append("(s.code LIKE ? OR s.symbol LIKE ? OR s.name LIKE ? OR s.industry LIKE ?)")
            pattern = f"%{term}%"
            params.extend([pattern] * 4)
        order = "b.total_mv ASC" if small_cap else "s.code ASC"
        sql = (
            "SELECT s.code,s.name,s.industry,b.close,b.pe_ttm,b.pb,b.dv_ttm,b.total_mv,b.trade_date "
            "FROM security_master s LEFT JOIN stock_daily_basic b ON b.code=s.code "
            "AND b.trade_date=(SELECT MAX(x.trade_date) FROM stock_daily_basic x WHERE x.code=s.code) "
            f"WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT ?"
        )
        params.append(limit)
        with self.store._lock:
            rows = self.store._conn.execute(sql, params).fetchall()
        return PublicSearchResult(
            query=query,
            interpretation=interpretations,
            items=[
                PublicSearchItem(
                    code=row["code"], name=row["name"], industry=row["industry"],
                    close=self._float(row["close"]), pe_ttm=self._float(row["pe_ttm"]),
                    pb=self._float(row["pb"]), dividend_yield=self._float(row["dv_ttm"]),
                    total_market_value=self._float(row["total_mv"]), as_of=row["trade_date"],
                )
                for row in rows
            ],
        )

    def stock(self, code: str) -> PublicStockSummary:
        lookup = code.strip().upper()
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT s.code,s.name,s.industry,s.market,b.close,b.pe_ttm,b.pb,b.dv_ttm,b.total_mv,b.trade_date "
                "FROM security_master s LEFT JOIN stock_daily_basic b ON b.code=s.code "
                "AND b.trade_date=(SELECT MAX(x.trade_date) FROM stock_daily_basic x WHERE x.code=s.code) "
                "WHERE s.code=? OR s.symbol=? ORDER BY b.trade_date DESC LIMIT 1",
                (lookup, lookup),
            ).fetchone()
        if row is None:
            raise InstrumentNotFound(lookup)
        return PublicStockSummary(
            code=row["code"], name=row["name"], industry=row["industry"], market=row["market"],
            close=self._float(row["close"]), pe_ttm=self._float(row["pe_ttm"]), pb=self._float(row["pb"]),
            dividend_yield=self._float(row["dv_ttm"]), total_market_value=self._float(row["total_mv"]),
            as_of=row["trade_date"],
        )

    def fund(self, code: str) -> PublicFundSummary:
        lookup = code.strip().upper()
        with self.store._lock:
            master = self.store._conn.execute(
                "SELECT code,name,type FROM fund_master WHERE code=?", (lookup,)
            ).fetchone()
            if master is None:
                raise InstrumentNotFound(lookup)
            table = "etf_daily" if str(master["type"] or "").upper() == "ETF" else "fund_daily"
            row = self.store._conn.execute(
                f"SELECT close, {'rise' if table == 'etf_daily' else 'rise_rate'} AS change_percent, trade_date "
                f"FROM {table} WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (lookup,),
            ).fetchone()
        return PublicFundSummary(
            code=master["code"], name=master["name"], fund_type=master["type"],
            close=self._float(row["close"]) if row else None,
            change_percent=self._float(row["change_percent"]) if row else None,
            as_of=row["trade_date"] if row else None,
        )

    @staticmethod
    def _float(value) -> float | None:
        return float(value) if value is not None else None
