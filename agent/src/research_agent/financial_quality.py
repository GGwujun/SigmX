"""Read-only financial-quality screening over normalized local statements."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any


_CASHFLOW_KEY = "经营活动产生的现金流量净额"
_PROFIT_KEYS = ("归属于母公司所有者的净利润", "净利润")


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number


class FinancialQualityResearch:
    """Calculate repeatable cash-flow quality metrics with evidence IDs."""

    def __init__(self, db_path: str | Path, *, classification_db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.classification_db_path = Path(classification_db_path) if classification_db_path else self.db_path

    def screen(self, *, limit: int = 20, periods_required: int = 2) -> dict[str, Any]:
        if periods_required < 2:
            raise ValueError("periods_required must be at least 2")
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            securities = {
                row["code"]: (row["name"], row["industry"] or "未分类")
                for row in conn.execute(
                    "SELECT code,name,industry FROM security_master WHERE is_active=1 "
                    "AND COALESCE(is_st,0)=0 AND COALESCE(is_delisting,0)=0"
                )
            }
            rows = conn.execute(
                "SELECT code,report_date,report_type,payload_json FROM financial_statement "
                "WHERE report_type IN ('llb','lrb') ORDER BY code,report_date DESC"
            ).fetchall()
        finally:
            conn.close()

        # Financial statements can temporarily live in the sync shadow while
        # the published DB owns the richer industry board mapping. Enrich from
        # that stable classification source and exclude genuinely unclassified
        # companies from an industry-relative calculation.
        classification_uri = f"file:{self.classification_db_path.as_posix()}?mode=ro"
        class_conn = sqlite3.connect(classification_uri, uri=True, timeout=30)
        class_conn.row_factory = sqlite3.Row
        try:
            direct = {
                row["code"]: (row["name"], row["industry"])
                for row in class_conn.execute(
                    "SELECT code,name,industry FROM security_master WHERE is_active=1"
                )
            }
            board_industries: dict[str, str] = {}
            try:
                board_industries = {
                    row["stock_code"]: row["name"]
                    for row in class_conn.execute(
                        "SELECT bm.stock_code,b.name FROM board_members bm "
                        "JOIN board_master b ON b.code=bm.board_code "
                        "WHERE bm.board_type='industry' AND b.name IS NOT NULL"
                    )
                }
            except sqlite3.OperationalError:
                pass
        finally:
            class_conn.close()
        securities = {
            code: (
                direct.get(code, (name, None))[0] or name,
                direct.get(code, (None, None))[1] or board_industries.get(code) or industry,
            )
            for code, (name, industry) in securities.items()
        }

        cashflows: dict[str, list[tuple[str, float]]] = defaultdict(list)
        profits: dict[tuple[str, str], float] = {}
        for row in rows:
            if row["code"] not in securities:
                continue
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if row["report_type"] == "llb":
                value = _number(payload.get(_CASHFLOW_KEY))
                if value is not None:
                    cashflows[row["code"]].append((row["report_date"], value))
            else:
                value = next((_number(payload.get(key)) for key in _PROFIT_KEYS if _number(payload.get(key)) is not None), None)
                if value is not None:
                    profits[(row["code"], row["report_date"])] = value

        metrics: list[dict[str, Any]] = []
        for code, series in cashflows.items():
            latest_by_date = list(dict.fromkeys(date for date, _ in series))[:periods_required]
            if len(latest_by_date) < periods_required:
                continue
            lookup = dict(series)
            chronological = [(date, lookup[date]) for date in reversed(latest_by_date)]
            latest_date, latest_cashflow = chronological[-1]
            profit = profits.get((code, latest_date))
            if profit is None or profit <= 0:
                continue
            ratio = latest_cashflow / profit
            name, industry = securities[code]
            if not industry or industry == "未分类":
                continue
            metrics.append({
                "code": code, "name": name, "industry": industry,
                "cashflow_series": chronological,
                "cashflow_improving": all(b[1] > a[1] for a, b in zip(chronological, chronological[1:])),
                "net_profit": profit, "cashflow_profit_ratio": ratio,
                "as_of": latest_date,
            })

        medians: dict[str, float] = {}
        by_industry: dict[str, list[float]] = defaultdict(list)
        for item in metrics:
            by_industry[item["industry"]].append(item["cashflow_profit_ratio"])
        for industry, values in by_industry.items():
            medians[industry] = float(median(values))

        selected = [
            {**item, "industry_median": medians[item["industry"]]}
            for item in metrics
            if item["cashflow_improving"] and item["cashflow_profit_ratio"] > medians[item["industry"]]
        ]
        selected.sort(key=lambda item: item["cashflow_profit_ratio"] - item["industry_median"], reverse=True)
        selected = selected[: max(1, min(int(limit), 100))]
        evidence: list[dict[str, Any]] = []
        for item in selected:
            for date, value in item["cashflow_series"]:
                evidence.append({"id": f"{item['code']}:operating_cashflow:{date}", "code": item["code"],
                                 "field": "operating_cashflow", "value": value, "as_of": date,
                                 "source": "local_financial_statement"})
            evidence.extend((
                {"id": f"{item['code']}:net_profit:{item['as_of']}", "code": item["code"],
                 "field": "net_profit", "value": item["net_profit"], "as_of": item["as_of"],
                 "source": "local_financial_statement"},
                {"id": f"{item['code']}:cashflow_profit_ratio:{item['as_of']}", "code": item["code"],
                 "field": "cashflow_profit_ratio", "value": item["cashflow_profit_ratio"],
                 "benchmark": item["industry_median"], "as_of": item["as_of"],
                 "source": "calculated_from_local_financial_statement"},
            ))
        return {
            "method": "经营现金流连续两期增长，且最新现金流利润比高于同行业中位数",
            "coverage": {"companies_evaluated": len(metrics), "periods_required": periods_required,
                         "source": self.db_path.name},
            "candidates": selected,
            "evidence": evidence,
        }
