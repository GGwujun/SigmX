"""
SigmX data-sync 推送服务（替代 rsync 文件覆盖）。
读本地 market.db 增量数据，通过 http POST /market-sync/push 推送到服务器。
服务器应用用自己的连接写库，不覆盖文件，无句柄失效问题。

增量：按 trade_date 水位线推进（存本地 sync_meta 表，key=push:{table}:last_date）。
只推 trade_date > 水位线 的日期。历史已收盘数据不变，水位线设到最新日-1 即可。
"""
import json
import os
import sqlite3
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get("DB_PATH", "/data/market.db")
SERVER_URL = os.environ.get("SERVER_URL", "").rstrip("/")
PUSH_TOKEN = os.environ.get("MARKET_SYNC_PUSH_TOKEN", "").strip()
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", "300"))
BATCH = 1000
TZ_SH = timezone(timedelta(hours=8))

# 与服务器 PUSH_TABLES 保持一致（A类 wide / B类 per_code）
PUSH_TABLES = [
    "sector_capital_flow", "stock_capital_rank", "market_breadth_snapshot",
    "sector_snapshot", "global_market_index_daily", "us_theme_snapshot",
    "us_a_share_transmission", "premarket_news", "dragon_tiger", "stock_pool",
    "bars_daily", "index_daily",
]


def log(msg):
    print(f"[{datetime.now(TZ_SH).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_meta(conn, key):
    row = conn.execute("SELECT value FROM sync_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn, key, value):
    conn.execute(
        "INSERT OR REPLACE INTO sync_meta (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def export_rows(conn, table, trade_date):
    """按 trade_date 导出某表全部行，展开 extra_json（与服务器 _get_market_wide 一致）。"""
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE trade_date=?", (trade_date,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        extra = d.pop("extra_json", None)
        if extra:
            try:
                d.update(json.loads(extra))
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


def distinct_dates(conn, table, after):
    """trade_date > after 的所有日期，升序。after 为空则取最新 2 天（只推最新）。"""
    if after:
        rows = conn.execute(
            f"SELECT DISTINCT trade_date FROM {table} WHERE trade_date > ? ORDER BY trade_date",
            (after,),
        ).fetchall()
        return [r["trade_date"] for r in rows]
    # 首次：只推最新 2 个交易日（历史已正确，不推全量）
    rows = conn.execute(
        f"SELECT DISTINCT trade_date FROM {table} ORDER BY trade_date DESC LIMIT 2"
    ).fetchall()
    return sorted(r["trade_date"] for r in rows)


def post_push(table, trade_date, rows):
    """分批 POST 到服务器 /market-sync/push。全部成功返回 True。"""
    if not rows:
        return True
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        payload = json.dumps(
            {"table": table, "trade_date": trade_date, "rows": chunk},
            ensure_ascii=False,
        ).encode("utf-8")
        url = f"{SERVER_URL}/market-sync/push"
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8",
                     "X-Push-Token": PUSH_TOKEN},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if not body.get("ok"):
                    log(f"  push {table}/{trade_date} batch {i}: server said not ok: {body}")
                    return False
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            log(f"  push {table}/{trade_date} batch {i} failed: {exc}")
            return False
    return True


def sync_once():
    conn = get_conn()
    try:
        for table in PUSH_TABLES:
            # 检查表是否存在
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            last = get_meta(conn, f"push:{table}:last_date")
            dates = distinct_dates(conn, table, last)
            if not dates:
                continue
            for d in dates:
                rows = export_rows(conn, table, d)
                if not rows:
                    # 空日期也推进水位线，避免反复查空
                    set_meta(conn, f"push:{table}:last_date", d)
                    continue
                log(f"push {table} {d}: {len(rows)} rows")
                if post_push(table, d, rows):
                    set_meta(conn, f"push:{table}:last_date", d)
                    log(f"  done {table} {d}")
                else:
                    log(f"  FAILED {table} {d}, will retry next cycle")
                    break  # 该表中断，下个周期重试；不推进水位线
    finally:
        conn.close()


def main():
    log(f"=== SigmX data-sync push started ===")
    log(f"DB: {DB_PATH}")
    log(f"Server: {SERVER_URL}")
    log(f"Interval: {SYNC_INTERVAL}s")
    log(f"Token: {'set' if PUSH_TOKEN else 'none (server may require)'}")
    if not SERVER_URL:
        log("ERROR: SERVER_URL not set")
        return
    while True:
        try:
            sync_once()
        except Exception as exc:  # noqa: BLE001
            log(f"sync cycle error: {exc}")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
