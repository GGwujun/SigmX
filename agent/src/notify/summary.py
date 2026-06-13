"""Build a market summary for notification push.

Reuses existing data layers (fund premium scan + opportunity scanner) to
assemble a concise markdown digest. Used by the /notify/test endpoint so the
"test" message is actually useful (real market data), not a fixed string.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# China timezone (UTC+8) for display.
_CST = timezone(timedelta(hours=8))


def _fmt_pct(v: float | None) -> str:
    if v is None or v != v:  # NaN check
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fund_opps_section(limit: int = 3) -> str:
    """Top fund arbitrage opportunities by |premium|."""
    try:
        from src.data.fund_premium import scan_fund_premium
        rows = scan_fund_premium("ETF", min_abs_premium=1.0, limit=limit)
    except Exception as exc:
        logger.info("notify summary: fund scan failed: %s", exc)
        return ""
    if not rows:
        return ""
    lines = ["**基金折溢价机会**"]
    for r in rows:
        name = (r.get("name") or r.get("code", ""))[:12]
        lines.append(f"- {name} {r.get('code','')} 折溢价 {_fmt_pct(r.get('premium_rate'))}")
    return "\n".join(lines)


def _opps_section(limit: int = 3) -> str:
    """Top opportunities from the opportunity scanner."""
    try:
        from src.api.opportunity_routes import _fetch_top_stocks  # noqa: F401
    except Exception:
        return ""
    try:
        # The opportunity scanner pulls via mootdx; reuse its internal fetch.
        import src.api.opportunity_routes as opp
        items = opp._fetch_top_stocks(limit=30)
    except Exception as exc:
        logger.info("notify summary: opp scan failed: %s", exc)
        return ""
    # Sort by a simple proxy (change_pct desc) and take top N with a name.
    picked = [x for x in items if x.get("name")] [:limit]
    if not picked:
        return ""
    lines = ["**异动标的**"]
    for it in picked:
        name = str(it.get("name", ""))[:10]
        chg = it.get("change_pct") if "change_pct" in it else it.get("changepercent")
        lines.append(f"- {name} {_fmt_pct(chg)}")
    return "\n".join(lines)


def build_summary() -> tuple[str, str]:
    """Return (title, markdown_body) for the digest. Never raises."""
    now_cst = datetime.now(_CST).strftime("%m-%d %H:%M")
    title = f"SigmX 行情摘要 {now_cst}"

    sections: list[str] = []
    fund = _fund_opps_section()
    if fund:
        sections.append(fund)
    opp = _opps_section()
    if opp:
        sections.append(opp)
    if not sections:
        body = "（暂无可推送的行情数据）"
    else:
        body = "\n\n".join(sections)
    return title, body
