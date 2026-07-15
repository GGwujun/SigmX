from __future__ import annotations

from src.data import alpha_signals


class _Store:
    def __init__(self) -> None:
        class _Conn:
            def execute(self, sql, params):
                assert "board_members" in sql
                return self

            def fetchall(self):
                return [
                    {"stock_code": "600001.SH"},
                    {"stock_code": "600002.SH"},
                    {"stock_code": "600003.SH"},
                ]

        self._conn = _Conn()


def test_peer_codes_use_local_board_members_only(monkeypatch) -> None:
    import src.data.market_store as market_store

    monkeypatch.setattr(market_store, "get_market_store", lambda: _Store())

    assert alpha_signals._get_peer_codes("600000.SH", min_peers=2) == [
        "600001.SH",
        "600002.SH",
        "600003.SH",
    ]
