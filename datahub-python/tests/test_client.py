import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from sigmx_datahub import DataHubClient, DataHubError
from sigmx_datahub.cli import main


class Response:
    status = 200
    headers = {
        "X-Request-ID": "req-1",
        "X-DataHub-Credits-Charged": "3",
        "X-DataHub-Credits-Remaining": "997",
    }

    def read(self):
        return json.dumps({"ok": True, "data": [1]}).encode()

    def __enter__(self): return self
    def __exit__(self, *args): return None


def test_client_sends_bearer_and_returns_credit_metadata():
    captured = {}

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    client = DataHubClient("sxd_live_test_secret", base_url="https://data.sigmx.cn", opener=opener)
    result = client.get("/api/v1/stocks/daily", {"symbol": "600519.SH"})
    assert captured["request"].headers["Authorization"] == "Bearer sxd_live_test_secret"
    assert "symbol=600519.SH" in captured["request"].full_url
    assert result.credits_charged == 3 and result.credits_remaining == 997
    assert result.data["ok"] is True


def test_client_rejects_bad_credentials_and_insecure_remote_url():
    with pytest.raises(ValueError): DataHubClient("not-a-key")
    with pytest.raises(ValueError): DataHubClient("sxd_live_valid", base_url="http://data.example.com")
    DataHubClient("sxd_live_valid", base_url="http://127.0.0.1:8000")


def test_cli_uses_environment_key_without_printing_it(monkeypatch, capsys):
    monkeypatch.setenv("SIGMX_DATAHUB_KEY", "sxd_live_cli_secret")

    class FakeClient:
        def __init__(self, credential, base_url):
            assert credential == "sxd_live_cli_secret"
        def get(self, path, params):
            return type("Result", (), {"data": {"ok": True}, "request_id": "r", "credits_charged": 0, "credits_remaining": 10})()

    assert main(["get", "/api/v1/health"], client_cls=FakeClient) == 0
    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert "sxd_live_cli_secret" not in output
