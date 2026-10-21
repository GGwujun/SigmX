"""东财跨进程防限流（em_get/em_post/em_get_with_fallback）的行为测试。

全部 mock 网络（不发真实请求），锁文件隔离到 tmp_path，节流间隔缩短
到 0.05s、抖动归零，让"串行间距来自锁内时间戳机制"可被精确断言。
"""

from __future__ import annotations

import threading
import types
from unittest import mock

import pytest

from src.data import astock_client as client
from src.data import capital_flow


@pytest.fixture(autouse=True)
def _isolated_lock(tmp_path, monkeypatch):
    """每个测试用独立锁文件 + 缩短间隔 + 抖动归零。"""
    monkeypatch.setattr(client, "EM_LOCK_PATH", str(tmp_path / "test-em.lock"))
    monkeypatch.setattr(client, "EM_MIN_INTERVAL", 0.05)
    fake_random = types.SimpleNamespace(uniform=lambda a, b: 0.0)
    monkeypatch.setattr(client, "random", fake_random)


def _fake_session(times: list[float]) -> mock.MagicMock:
    session = mock.MagicMock()
    resp = mock.MagicMock()
    resp.status_code = 200
    session.get.side_effect = lambda *a, **kw: times.append(threading.get_ident() * 0 + _now()) or resp
    return session


def _now() -> float:
    import time
    return time.time()


def test_em_get_serializes_threads_with_min_interval():
    """双线程并发调用：任意两次请求的实际间隔 ≥ EM_MIN_INTERVAL。"""
    times: list[float] = []
    with mock.patch.object(client, "EM_SESSION", _fake_session(times)):
        threads = [
            threading.Thread(target=lambda: [client.em_get("https://x") for _ in range(3)])
            for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert len(times) == 6
    ordered = sorted(times)
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    # 间距来自锁内时间戳机制；允许调度级误差。
    assert all(g >= client.EM_MIN_INTERVAL - 0.01 for g in gaps), gaps


def test_em_serial_persists_completion_timestamp(tmp_path):
    """调用完成后锁文件里留下可解析的完成时间戳。"""
    with mock.patch.object(client, "EM_SESSION", _fake_session([])):
        client.em_get("https://x")
    raw = (tmp_path / "test-em.lock").read_text().strip()
    assert float(raw) > 0


def test_em_post_uses_same_serial_path():
    """em_post 走同一把锁（POST 也被串行限流）。"""
    times: list[float] = []
    session = mock.MagicMock()
    resp = mock.MagicMock()
    session.post.side_effect = lambda *a, **kw: times.append(_now()) or resp
    with mock.patch.object(client, "EM_SESSION", session):
        client.em_post("https://x", json_body={"a": 1})
        client.em_post("https://x", json_body={"b": 2})
    assert len(times) == 2
    assert times[1] - times[0] >= client.EM_MIN_INTERVAL - 0.01


def test_em_get_with_fallback_switches_host_on_connection_error():
    """push2 连接类失败 → 自动改打 push2delay；两台都挂才抛。"""
    ok = mock.MagicMock()
    ok.status_code = 200
    with mock.patch.object(
        client, "em_get",
        side_effect=[client.requests.exceptions.ConnectionError("push2 down"), ok],
    ) as fake_get:
        resp = client.em_get_with_fallback(
            "https://push2.eastmoney.com/api/qt/clist/get", params={"fid": "f62"})
    assert resp is ok
    hosts = [c.args[0] for c in fake_get.call_args_list]
    assert hosts == [
        "https://push2.eastmoney.com/api/qt/clist/get",
        "https://push2delay.eastmoney.com/api/qt/clist/get",
    ]


def test_em_get_with_fallback_does_not_switch_host_on_http_status():
    """HTTP 状态码（如 403）原样返回，不换主机——换主机只会放大风控。"""
    forbidden = mock.MagicMock()
    forbidden.status_code = 403
    with mock.patch.object(client, "em_get", return_value=forbidden) as fake_get:
        resp = client.em_get_with_fallback("https://push2his.eastmoney.com/api/qt/kline/get")
    assert resp is forbidden
    assert fake_get.call_count == 1


def test_em_get_with_fallback_raises_when_all_hosts_down():
    err = client.requests.exceptions.ConnectionError("all down")
    with mock.patch.object(client, "em_get", side_effect=err):
        with pytest.raises(client.requests.exceptions.ConnectionError):
            client.em_get_with_fallback("https://push2.eastmoney.com/api/qt/clist/get")


def test_popularity_goes_through_em_post():
    """人气榜从裸 urllib 收编到 em_post（共用跨进程锁）。"""
    resp = mock.MagicMock()
    resp.json.return_value = {"data": [
        {"sc": "SZ002384", "rk": 1, "rc": 2, "hisRc": 3},
        {"sc": "SH600519", "rk": 5, "rc": -1, "hisRc": 0},
    ]}
    with mock.patch.object(client, "em_post", return_value=resp) as fake_post:
        rows = client.eastmoney_popularity(page_size=2)
    assert rows[0] == {"code": "002384", "market": "SZ", "rank": 1,
                       "rank_change": 2, "history_rank_change": 3}
    assert "emappdata.eastmoney.com" in fake_post.call_args.args[0]
    assert fake_post.call_args.kwargs["json_body"]["pageSize"] == 2


def test_popularity_empty_on_error():
    with mock.patch.object(client, "em_post", side_effect=RuntimeError("boom")):
        assert client.eastmoney_popularity() == []


def test_eps_forecast_goes_through_em_get():
    """EPS 一致预期从裸 urllib 收编到 em_get（共用跨进程锁）。"""
    import datetime as _dt
    year = _dt.date.today().year
    resp = mock.MagicMock()
    resp.json.return_value = {"data": [
        {"title": "r1", "predictThisYearEps": "3.10", "predictNextYearEps": "3.60"},
        {"title": "r2", "predictThisYearEps": "3.20", "predictNextYearEps": ""},
    ]}
    with mock.patch.object(client, "em_get", return_value=resp) as fake_get:
        rows = client.eastmoney_eps_forecast("600519", max_pages=1)
    by_year = {r["year"]: r for r in rows}
    assert by_year[str(year)]["count"] == 2
    assert by_year[str(year)]["mean_eps"] == pytest.approx(3.15)
    assert by_year[str(year + 1)]["count"] == 1  # 空串不留数
    assert "reportapi.eastmoney.com" in fake_get.call_args.args[0]


def test_eps_forecast_empty_on_error():
    with mock.patch.object(client, "em_get", side_effect=RuntimeError("boom")):
        assert client.eastmoney_eps_forecast("600519", max_pages=1) == []


def test_capital_flow_libraries_share_the_global_em_lock(monkeypatch):
    """akshare/efinance 的库调用被包进 em_get 同一把锁（_em_serial）。"""
    wrapped: list[bool] = []

    def fake_unit(fn):
        wrapped.append(True)
        return fn()

    monkeypatch.setattr(capital_flow, "_paced_em_unit", fake_unit)

    import pandas as pd
    fake_ef = types.ModuleType("efinance")
    fake_ef.stock = types.SimpleNamespace(get_history_bill=lambda code: pd.DataFrame({
        "日期": ["2026-10-20"],
        "主力净流入-净额": [1.2],
        "主力净流入-净占比": [3.4],
        "超大单净流入-净额": [0.5],
        "大单净流入-净额": [0.7],
        "中单净流入-净额": [-0.1],
        "小单净流入-净额": [-0.2],
    }))
    monkeypatch.setitem(__import__("sys").modules, "efinance", fake_ef)

    rows = capital_flow.get_stock_capital("600519", days=5)
    assert rows and rows[0]["main_net"] == 1.2
    assert wrapped == [True]  # 库调用确实在锁内执行
