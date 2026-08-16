"""Limited, anonymous Web research reads over the local public market store."""

from __future__ import annotations

from dataclasses import dataclass

from src.data.market_store import MarketStore
from src.product.query_intent import IntentKind, parse_query


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
    instrument_type: str = "stock"


@dataclass(frozen=True)
class PublicResourceLink:
    title: str
    url: str
    description: str


@dataclass(frozen=True)
class PublicSearchResult:
    query: str
    interpretation: list[str]
    items: list[PublicSearchItem]
    intent: str = "instrument_search"
    answer: str | None = None
    resources: tuple[PublicResourceLink, ...] = ()
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
        intent = parse_query(query)
        query = intent.normalized_query
        limit = min(max(int(limit), 1), 10)
        if intent.kind is IntentKind.MARKET_QUESTION:
            return self._market_answer(query)
        if intent.kind is IntentKind.API_DOCS:
            return self._docs_answer(query)
        if intent.kind is IntentKind.FUND_SEARCH:
            return self._fund_search(query, limit)
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
            intent=intent.kind.value,
        )

    def _market_answer(self, query: str) -> PublicSearchResult:
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT trade_date, COUNT(*) AS instruments, "
                "SUM(CASE WHEN close > open THEN 1 ELSE 0 END) AS advances, "
                "SUM(CASE WHEN close < open THEN 1 ELSE 0 END) AS declines "
                "FROM bars_daily WHERE trade_date=(SELECT MAX(trade_date) FROM bars_daily) GROUP BY trade_date"
            ).fetchone()
        if row is None:
            answer = "市场概览数据暂不可用。"
        else:
            answer = (
                f"{row['trade_date']} 可用样本 {int(row['instruments'] or 0)} 个，"
                f"上涨 {int(row['advances'] or 0)} 个，下跌 {int(row['declines'] or 0)} 个。"
            )
        return PublicSearchResult(
            query=query,
            interpretation=["识别为市场概览问题"],
            items=[],
            intent=IntentKind.MARKET_QUESTION.value,
            answer=answer,
        )

    @staticmethod
    def _docs_answer(query: str) -> PublicSearchResult:
        resources = (
            PublicResourceLink("股票日线接口", "/docs/data-hub/stocks-daily", "历史日线、复权与质量字段"),
            PublicResourceLink("Data Hub 快速开始", "/docs/data-hub/quickstart", "认证、SDK 和 Data Credit 计费"),
        )
        return PublicSearchResult(
            query=query,
            interpretation=["识别为 Data Hub 文档问题"],
            items=[],
            intent=IntentKind.API_DOCS.value,
            answer="可从股票日线接口文档和快速开始继续。",
            resources=resources,
        )

    def _fund_search(self, query: str, limit: int) -> PublicSearchResult:
        text = query
        for marker in ("ETF", "etf", "LOF", "lof", "基金", "折溢价"):
            text = text.replace(marker, " ")
        terms = [term for term in text.split() if term]
        clauses = []
        params: list[object] = []
        for term in terms:
            clauses.append("(code LIKE ? OR name LIKE ? OR type LIKE ?)")
            params.extend([f"%{term}%"] * 3)
        where = " AND ".join(clauses) if clauses else "1=1"
        params.append(limit)
        with self.store._lock:
            masters = self.store._conn.execute(
                f"SELECT code,name,type FROM fund_master WHERE {where} ORDER BY code LIMIT ?", params
            ).fetchall()
            items = []
            for master in masters:
                table = "etf_daily" if str(master["type"] or "").upper() == "ETF" else "fund_daily"
                daily = self.store._conn.execute(
                    f"SELECT close,trade_date FROM {table} WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                    (master["code"],),
                ).fetchone()
                items.append(PublicSearchItem(
                    code=master["code"], name=master["name"], industry=master["type"],
                    close=self._float(daily["close"]) if daily else None,
                    pe_ttm=None, pb=None, dividend_yield=None, total_market_value=None,
                    as_of=daily["trade_date"] if daily else None, instrument_type="fund",
                ))
        return PublicSearchResult(
            query=query,
            interpretation=["识别为 ETF/LOF/基金搜索"],
            items=items,
            intent=IntentKind.FUND_SEARCH.value,
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
