"""短线计算快照：纯函数口径 + 同步落库两分支（盘中只 live / 收盘全量）。

合成行全部用池表列名（zt_pool/zb_pool/dt_pool/yzt_pool 建表列），照
test_stage_snapshot 的"seed 输入表 → 跑同步 → 断言落库"模式，全程无网络。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data import market_sync as ms
from src.data import shortline_metrics as sm
from src.data.market_store import MarketStore


@pytest.fixture
def store(tmp_path: Path) -> MarketStore:
    s = MarketStore(tmp_path / "market.db")
    yield s
    s._conn.close()


# ---------------------------------------------------------------------------
# 制度规则工具
# ---------------------------------------------------------------------------

def test_board_of_by_code_prefix_and_st() -> None:
    assert sm.board_of("430047.BJ", "北交所个股") == "北交所"
    assert sm.board_of("920001.BJ", "北证新股") == "北交所"
    assert sm.board_of("300750.SZ", "宁德时代") == "20cm"
    assert sm.board_of("688981.SH", "中芯国际") == "20cm"
    assert sm.board_of("300126.SZ", "ＳＴ 锐电") == "20cm(ST)"  # NFKC 全角归一
    assert sm.board_of("600000.SH", "ST 浦发") == "主板ST"
    assert sm.board_of("600000.SH", "浦发银行") == "10cm"


def test_limit_pct_uses_day_dependent_rules() -> None:
    # 创业板 2020-08-24 注册制前后 10%→20%
    assert sm.limit_pct("300750.SZ", "宁德时代", "2020-08-21") == 10.0
    assert sm.limit_pct("300750.SZ", "宁德时代", "2020-08-24") == 20.0
    # 主板 ST 2026-07-06 新规前后 5%→10%
    assert sm.limit_pct("600000.SH", "ST浦发", "2026-07-03") == 5.0
    assert sm.limit_pct("600000.SH", "ST浦发", "2026-07-06") == 10.0
    # 北交所 30%、科创 20%、普通主板 10%
    assert sm.limit_pct("430047.BJ", "北交所", "2026-07-15") == 30.0
    assert sm.limit_pct("688981.SH", "中芯", "2026-07-15") == 20.0
    assert sm.limit_pct("600000.SH", "浦发", "2026-07-15") == 10.0


def test_board_label_marks_fanbao_only_when_days_exceeds_boards() -> None:
    assert sm.board_label("5天3板", 1) == "5天3板"  # 反包：days>ct
    assert sm.board_label("3/2", 1) == "3天2板"
    assert sm.board_label("3天3板", 3) == "3板"  # 非反包退化为 N板
    assert sm.board_label("", 2) == "2板"
    assert sm.stat_boards("5天3板", 1) == 3
    assert sm.stat_boards("", 4) == 4


# ---------------------------------------------------------------------------
# 合成行工厂（列名与池表一致）
# ---------------------------------------------------------------------------

def _zt(code: str, boards: int, *, pct: float = 10.0, industry: str = "电池",
        first_seal: str = "093000", last_seal: str = "093000",
        break_times: int = 0, zt_stat: str = "", name: str = "样本") -> dict:
    return {"code": code, "name": name, "price": 10.0, "pct": pct, "amount": 1e8,
            "float_cap": 5e9, "turnover": 2.0, "limit_days": boards,
            "first_seal": first_seal, "last_seal": last_seal, "seal_fund": 1e8,
            "break_times": break_times, "industry": industry, "zt_stat": zt_stat}


def _yzt(code: str, ret: float | None, *, prev_boards: int = 1,
         industry: str = "电池", seal: str = "093000") -> dict:
    return {"code": code, "name": "样本", "price": 10.0, "pct": ret, "turnover": 2.0,
            "amplitude": 3.0, "speed": 0.5, "y_first_seal": seal,
            "y_limit_days": prev_boards, "industry": industry, "zt_stat": ""}


def _zb(code: str, *, industry: str = "电池", zt_stat: str = "") -> dict:
    return {"code": code, "name": "样本", "price": 9.9, "limit_price": 10.0,
            "pct": 5.0, "turnover": 3.0, "first_seal": "093500",
            "break_times": 1, "amplitude": 6.0, "speed": 0.4,
            "industry": industry, "zt_stat": zt_stat}


# ---------------------------------------------------------------------------
# A 组 8 个纯函数
# ---------------------------------------------------------------------------

def test_build_emotion_four_blocks() -> None:
    zt = [_zt("A", 1), _zt("B", 2), _zt("Z", 4, industry="地产")]
    prev_zt = [_zt("A", 1), _zt("B", 2), _zt("C", 3), _zt("D", 1), _zt("E", 5)]
    yzt = [
        _yzt("A", 10.0, prev_boards=1),   # 又涨停（在今日 zt 池）
        _yzt("B", 3.0, prev_boards=2),    # 2 板以上 → consec_premium 样本
        _yzt("C", -6.0, prev_boards=3),   # 今日不在 zt 池
        _yzt("F", None, prev_boards=1),   # 缺 ret → coverage partial
    ]
    out = sm.build_emotion("2026-07-15", "2026-07-14", zt, prev_zt, yzt)

    me = out["money_effect"]
    assert me["available"] is True and me["source"] == "settled"
    assert me["sample"] == 3 and me["expected_sample"] == 4
    assert me["partial"] is True and me["coverage_rate"] == 0.75
    assert me["limit_up_again_rate"] == round(2 / 3, 3)

    promo = out["promotion"]
    assert promo["tiers"]["1进2"] == {"base": 2, "promoted": 1, "rate": 0.5}
    assert promo["tiers"]["2进3"] == {"base": 1, "promoted": 1, "rate": 1.0}
    assert promo["tiers"]["3板以上晋级"] == {"base": 2, "promoted": 0, "rate": 0.0}
    assert promo["overall"] == {"base": 5, "promoted": 2, "rate": 0.4}

    cp = out["consec_premium"]
    assert cp["available"] is True and cp["sample"] == 2
    assert cp["median"] == round((3.0 + -6.0) / 2, 2)

    gap = out["ladder_gap"]
    assert gap["highest"] == 4
    assert gap["tiers"] == {"4": 1, "2": 1}
    assert gap["gaps"] == [3] and gap["continuous"] is False


def test_build_daily_readings() -> None:
    zt = [_zt("A", 1), _zt("B", 3)]
    zb = [_zb("X")]
    prev_zt = [_zt("A", 1), _zt("B", 1), _zt("D", 1)]  # 三只首板
    yzt = [_yzt("A", 10.0), _yzt("B", -6.0), _yzt("D", -1.0)]
    out = sm.build_daily("2026-07-15", "2026-07-14", zt, zb, yzt, prev_zt)

    r = out["readings"]
    assert r["limit_up"] == 2 and r["highest_board"] == 3
    assert r["broken_rate"] == round(1 / 3, 3)
    assert r["money_effect"] == -1.0  # 中位数
    assert r["deep_loss"] == 1
    assert r["promotion_1to2"] == round(2 / 3, 3)  # A、B 晋级，D 落队
    assert out["promotion_base"] == 3 and out["promotion_promoted"] == 2
    assert out["reasons"] == {}


def test_build_daily_with_empty_pools_degrades() -> None:
    out = sm.build_daily("2026-07-15", "2026-07-14", [], [], [], [])
    assert out["readings"]["limit_up"] == 0
    assert out["readings"]["broken_rate"] is None
    assert out["readings"]["money_effect"] is None
    assert out["readings"]["promotion_1to2"] is None
    assert out["reasons"]["promotion"] and out["reasons"]["settled"]


def test_build_facts_tables() -> None:
    zt = [
        _zt("A", 1, first_seal="092800", break_times=0),
        _zt("B", 3, first_seal="145500", last_seal="145500", break_times=2, industry="地产"),
        _zt("C", 2, first_seal="100500", industry="地产"),
    ]
    zb = [_zb("X", industry="地产")]
    dt = [{"code": "D", "name": "样本", "price": 5.0, "pct": -10.0, "turnover": 1.0,
           "pe": 5.0, "seal_fund": 1e8, "board_amount": 1e8, "dt_days": 2,
           "open_times": 1, "industry": "地产"}]
    yzt = [
        _yzt("B", 10.0, prev_boards=3, industry="地产"),   # 晋级涨停
        _yzt("D", -10.0, prev_boards=2, industry="地产"),  # 跌停
        _yzt("E", -6.5, prev_boards=1),                    # 跌超5%
        _yzt("F", 2.0, prev_boards=1),                     # 收红
    ]
    prev_zt = [_zt("B", 3), _zt("D", 2)]
    out = sm.build_facts("2026-07-15", "2026-07-14", zt, zb, dt, yzt, prev_zt)

    sq = out["seal_quality"]
    assert sq["total"] == 3 and sq["never_broken"] == 2
    assert sq["opening_seconds"] == 1  # A 09:28
    assert sq["late_seal"] == 1  # B 14:55
    assert sq["reopened"] == 1 and sq["avg_broken_times"] == round(2 / 3, 2)

    le = out["loss_effect"]
    assert le["deep_loss_5_count"] == 2 and le["limit_down_count"] == 1
    assert le["market_limit_down"] == 1 and le["worst"] == -10.0

    matrix = out["feedback"]["matrix"]
    assert matrix["3板"]["晋级涨停"] == 1
    assert matrix["2板"]["跌停"] == 1
    assert matrix["首板"]["跌超5%"] == 1 and matrix["首板"]["收红"] == 1
    # details 按涨跌幅升序（最差在前）
    assert out["feedback"]["details"][0]["code"] in ("B", "D")

    themes = out["themes"]
    assert themes["theme_count"] == 2
    assert themes["groups"]["电池"]["limit_up"] == 1
    assert themes["groups"]["地产"]["broken"] == 1
    assert themes["timeline"][0]["count"] == 1  # 09:25-09:35 槽 A

    tags = [e["tag"] for e in out["events"]]
    assert "最高标" in tags and "反复开板" in tags and "题材首封" in tags
    assert "高标跌停" in tags  # D prev_boards=2

    bb = out["by_board"]
    assert bb["10cm"]["limit_up"] == 3
    assert bb["10cm"]["prev_base"] == 2 and bb["10cm"]["promoted"] == 1


def test_build_structure_mix_respects_day_rules() -> None:
    zt = [
        _zt("600001.SH", 1),                    # 主板 10%
        _zt("300750.SZ", 2),                    # 创业板 → 20%
        _zt("430047.BJ", 3, name="北交所"),     # 北交所
    ]
    out = sm.build_structure("2026-07-15", zt, [], [], [])
    assert out["mix"] == {"20%": 1, "10%": 1, "北交所": 1}
    assert out["share_20cm"] == round(1 / 3, 3)
    assert out["highest_board"] == 3
    assert out["leaders"][0]["code"] == "430047.BJ"
    # 2020-08-21 的创业板仍按 10% 归类
    old = sm.build_structure("2020-08-21", [_zt("300750.SZ", 2)], [], [], [])
    assert old["mix"]["10%"] == 1 and old["mix"]["20%"] == 0


def test_build_ladder_reads_prev_day_pool() -> None:
    prev = [
        _zt("A", 5, zt_stat="6天5板"),
        _zt("B", 2),
        _zt("C", 2),
        _zt("D", 1),
    ]
    out = sm.build_ladder("2026-07-15", "2026-07-14", prev)
    assert out["available"] is True
    assert out["sample_date"] == "2026-07-14"
    assert out["highest"] == 5 and out["total"] == 4
    assert out["stocks"][0]["label"] == "6天5板"
    assert out["tiers"] == [{"boards": 5, "count": 1}, {"boards": 2, "count": 2},
                            {"boards": 1, "count": 1}]
    # 空样本：东财池历史窗口外的常见形态
    empty = sm.build_ladder("2026-07-15", None, [])
    assert empty["available"] is False and empty["stocks"] == []


def test_build_settled_expected_includes_missing_ret() -> None:
    yzt = [
        _yzt("A", 9.98, prev_boards=2),
        _yzt("B", None, prev_boards=1),
        _yzt("C", -3.0, prev_boards=4),
    ]
    out = sm.build_settled("2026-07-15", "2026-07-14", yzt)
    cov = out["settled_cov"]
    assert cov["sample"] == 2 and cov["expected_sample"] == 3
    assert cov["partial"] is True
    rows = out["rows"]
    assert rows[0]["prev_boards"] == 4  # 按 prev_boards 降序
    # A 是主板 10cm、ret 9.98 ≥ 9.7 → 按幅度推定涨停
    assert next(r for r in rows if r["code"] == "A")["limit_up"] is True
    # B 缺 ret 且无涨停价 → None
    assert next(r for r in rows if r["code"] == "B")["limit_up"] is None


def test_build_cycle_normalization_and_dropped_days() -> None:
    def _day(zt_count: int, zb_count: int) -> tuple[list[dict], list[dict]]:
        zts = [_zt(f"C{i}", 1 + (i % 3)) for i in range(zt_count)]
        zbs = [_zb(f"Z{i}") for i in range(zb_count)]
        return zts, zbs

    window = []
    for i, (nz, nb) in enumerate([(5, 2), (8, 1), (12, 0), (15, 1), (20, 3)]):
        day = f"2026-07-{10 + i:02d}"
        zts, zbs = _day(nz, nb)
        window.append((day, zts, zbs))
    # 中间塞一个空 zt 日 → 丢弃
    window.insert(2, ("2026-07-99", [], []))

    out = sm.build_cycle("2026-07-14", window, requested_window=10)
    assert out["available"] is True
    assert out["window"] == 5  # 空日被丢
    assert len(out["series"]) == 5
    assert out["trough_date"] == "2026-07-10"  # 首日 score 最低
    assert out["day_n"] == 4 and out["rising"] is True
    assert all("score" in s for s in out["series"])

    short = sm.build_cycle("2026-07-14", window[:2], requested_window=10)
    assert short["available"] is False


def test_build_live_snapshot_fields() -> None:
    zt = [_zt("A", 1), _zt("B", 2)]
    prev_zt = [_zt("A", 1), _zt("D", 1), _zt("B", 2)]
    zb = [_zb("X")]
    yzt = [_yzt("A", 5.0), _yzt("D", -6.0)]
    out = sm.build_live("2026-07-15", "in_session", "2026-07-15T10:00:00+08:00",
                        zt, zb, [], yzt, prev_zt)
    assert out["available"] is True
    assert out["limit_up"] == 2 and out["broken"] == 1 and out["limit_down"] is None
    assert out["seal_rate"] == round(2 / 3, 3)
    assert out["promotion_all"] == {"base": 3, "promoted": 2, "rate": round(2 / 3, 3)}
    assert out["promotion_1to2"]["base"] == 2
    assert out["money_effect"]["median"] == round((5.0 + -6.0) / 2, 2)
    assert out["deep_loss"] == 1
    empty = sm.build_live("2026-07-15", "pre_open", "x", [], [], [], [], [])
    assert empty["available"] is False


# ---------------------------------------------------------------------------
# 同步落库：盘中只 live / 收盘全量（照 test_stage_snapshot 模式）
# ---------------------------------------------------------------------------

def _seed_calendar(store: MarketStore, days: list[str]) -> None:
    with store._write_transaction():
        for d in days:
            store._conn.execute(
                "INSERT OR REPLACE INTO trade_calendar (trade_date, is_trading, market, updated_at) "
                "VALUES (?, 1, 'CN', '2026-07-15T16:00:00')", (d,))


def _seed_pools(store: MarketStore, trade_date: str, prev_date: str) -> None:
    store.upsert_zt_pool(trade_date, [
        _zt("600001.SH", 1, industry="银行", first_seal="092500"),
        _zt("600002.SH", 2, industry="电池"),
        _zt("600003.SH", 5, industry="电池", zt_stat="6天5板"),
    ], source="eastmoney")
    store.upsert_zt_pool(prev_date, [
        _zt("600001.SH", 1, industry="银行"),
        _zt("600002.SH", 1, industry="电池"),
        _zt("600003.SH", 4, industry="电池", zt_stat="5天4板"),
    ], source="eastmoney")
    store.upsert_zb_pool(trade_date, [_zb("600004.SH", industry="电池")])
    store.upsert_yzt_pool(trade_date, [
        _yzt("600001.SH", 10.0, prev_boards=1, industry="银行"),
        _yzt("600002.SH", -6.0, prev_boards=1, industry="电池"),
    ])


def test_sync_shortline_intraday_phase_writes_only_live(
    store: MarketStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = ms._today_cst_str()
    prev = "2026-07-14"
    _seed_calendar(store, [prev, today])
    _seed_pools(store, today, prev)
    monkeypatch.setattr("src.data.trade_calendar.cn_market_phase", lambda *a, **k: "in_session")

    result = ms._sync_shortline_snapshots(store, today)

    assert result == {"shortline": 1}
    kinds = {r["kind"] for r in store._conn.execute(
        "SELECT kind FROM shortline_snapshot WHERE trade_date = ?", (today,))}
    assert kinds == {"live"}
    payload = store.get_shortline_snapshot("live", today)["payload"]
    assert payload["available"] is True and payload["phase"] == "in_session"
    assert payload["limit_up"] == 3


def test_sync_shortline_post_close_writes_all_review_kinds(
    store: MarketStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    trade_date = "2026-07-15"
    days = [f"2026-07-{d:02d}" for d in range(6, 16)]  # 10 个交易日给 cycle 窗口
    _seed_calendar(store, days)
    for i, d in enumerate(days):
        store.upsert_zt_pool(d, [_zt("600001.SH", 1 + i % 3)], source="eastmoney")
        store.upsert_zb_pool(d, ([_zb("600004.SH")] if i % 2 else []))
    _seed_pools(store, trade_date, "2026-07-14")
    monkeypatch.setattr("src.data.trade_calendar.cn_market_phase", lambda *a, **k: "post_close")

    result = ms._sync_shortline_snapshots(store, trade_date)

    assert result == {"shortline": 8}
    rows = {r["kind"]: r for r in store._conn.execute(
        "SELECT kind, payload_json FROM shortline_snapshot WHERE trade_date = ?",
        (trade_date,))}
    assert set(rows) == {"emotion", "daily", "facts", "structure",
                         "ladder", "settled", "cycle", "live"}
    emotion = store.get_shortline_snapshot("emotion", trade_date)["payload"]
    assert emotion["money_effect"]["available"] is True

    ladder = store.get_shortline_snapshot("ladder", trade_date)
    assert ladder["payload"]["sample_date"] == "2026-07-14"
    assert ladder["payload"]["highest"] == 4

    cycle = store.get_shortline_snapshot("cycle", trade_date)
    assert cycle["payload"]["available"] is True
    assert len(cycle["payload"]["series"]) == 10

    # 幂等：重跑不涨行数（PK 覆盖）
    assert ms._sync_shortline_snapshots(store, trade_date) == {"shortline": 8}


def test_run_daily_sync_dispatches_shortline_dataset(
    store: MarketStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        ms, "_sync_shortline_snapshots",
        lambda target, date: calls.append("shortline") or 8,
    )
    result = ms.run_daily_sync("2026-07-15", store=store,
                               datasets={"shortline"}, sync_run_id="run-1")
    assert result == {"shortline": 8}
    assert calls == ["shortline"]
