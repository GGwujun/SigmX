import json
import sqlite3
from pathlib import Path

from src.research_agent.financial_quality import FinancialQualityResearch


def test_financial_quality_screens_cashflow_improvement_against_industry_median(tmp_path: Path) -> None:
    db = tmp_path / "market.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE security_master(code TEXT PRIMARY KEY,name TEXT,industry TEXT,is_active INTEGER,is_st INTEGER,is_delisting INTEGER);"
        "CREATE TABLE financial_statement(code TEXT,report_date TEXT,report_type TEXT,payload_json TEXT,updated_at TEXT);"
    )
    securities = [("A", "甲公司", "制造", 1, 0, 0), ("B", "乙公司", "制造", 1, 0, 0), ("C", "丙公司", "制造", 1, 0, 0)]
    conn.executemany("INSERT INTO security_master VALUES(?,?,?,?,?,?)", securities)
    for code, cashflows, profit in (("A", (80, 120), 100), ("B", (90, 100), 100), ("C", (100, 90), 100)):
        for date, value in zip(("2024-12-31", "2025-12-31"), cashflows):
            conn.execute("INSERT INTO financial_statement VALUES(?,?,?,?,?)", (code, date, "llb", json.dumps({"经营活动产生的现金流量净额": value}), date))
        conn.execute("INSERT INTO financial_statement VALUES(?,?,?,?,?)", (code, "2025-12-31", "lrb", json.dumps({"净利润": profit}), "2025-12-31"))
    conn.commit()
    conn.close()

    result = FinancialQualityResearch(db).screen(limit=10)

    assert [item["code"] for item in result["candidates"]] == ["A"]
    assert result["candidates"][0]["cashflow_profit_ratio"] == 1.2
    assert result["candidates"][0]["industry_median"] == 1.0
    assert len(result["evidence"]) >= 3
    assert result["coverage"]["periods_required"] == 2
