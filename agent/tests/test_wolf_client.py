"""Tests for the wolf (黑狼数据) HTTP client: token resolution, envelope-free
response normalization, and limiter discipline."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.data import wolf_client
from src.data.wolf_client import WolfNotConfiguredError, call, get_token, is_configured


def _fake_response(status=200, payload=None, text=""):
    r = mock.Mock()
    r.status_code = status
    r.text = text or str(payload)
    r.json = lambda: payload
    return r


class TestToken:
    def test_env_token(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        assert get_token() == "tok123"

    def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("WOLF_TOKEN", raising=False)
        with mock.patch.object(wolf_client, "_ENV_PATH", Path("C:/nonexistent/.env")):
            with pytest.raises(WolfNotConfiguredError):
                get_token()
        assert is_configured() is False

    def test_placeholder_token_raises(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "your-wolf-token")
        with pytest.raises(WolfNotConfiguredError):
            get_token()


class TestCall:
    def test_bare_array_response(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        with mock.patch("requests.get", return_value=_fake_response(
                payload=[{"code": "000001", "name": "平安银行"}])) as rg:
            rows = call("wolf/list", flag=0)
        assert rows == [{"code": "000001", "name": "平安银行"}]
        # token injected as query param, empty params dropped
        assert rg.call_args.kwargs["params"]["token"] == "tok123"
        assert rg.call_args.kwargs["params"]["flag"] == 0

    def test_single_object_wrapped(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        with mock.patch("requests.get", return_value=_fake_response(payload={"a": 1})):
            assert call("wolf/fq") == [{"a": 1}]

    def test_empty_normalizes_to_list(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        with mock.patch("requests.get", return_value=_fake_response(payload=None)):
            assert call("wolf/fq", tradeDate="2026-08-14") == []

    def test_non_200_raises(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        with mock.patch("requests.get", return_value=_fake_response(status=403, text="forbidden")):
            from src.data.wolf_client import WolfError
            with pytest.raises(WolfError, match="403"):
                call("wolf/list")

    def test_none_params_dropped(self, monkeypatch):
        monkeypatch.setenv("WOLF_TOKEN", "tok123")
        with mock.patch("requests.get", return_value=_fake_response(payload=[])) as rg:
            call("wolf/zt", tradeDate=None, symbol="")
        assert "tradeDate" not in rg.call_args.kwargs["params"]
        assert "symbol" not in rg.call_args.kwargs["params"]
