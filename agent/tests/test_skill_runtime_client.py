import json

import pytest

from src.skill_runtime.client import DataHubClient, SkillRuntimeError
from src.skill_runtime.models import DataRequest


def test_data_hub_client_sends_bearer_only_to_configured_origin():
    calls = []

    def transport(url, headers, timeout):
        calls.append((url, headers, timeout))
        return 200, json.dumps({"data": [{"code": "000001.SZ"}], "meta": {"as_of": "2026-08-25"}}).encode()

    result = DataHubClient("https://data.sigmx.cn", "sxd_live_secret", transport=transport).fetch(
        DataRequest("stocks.daily", {"code": "000001.SZ"})
    )

    assert calls == [("https://data.sigmx.cn/api/v1/stocks/daily?code=000001.SZ", {"Authorization": "Bearer sxd_live_secret", "Accept": "application/json"}, 15.0)]
    assert result.rows == ({"code": "000001.SZ"},)
    assert result.source == "sigmx_data_hub"
    assert result.as_of == "2026-08-25"


def test_data_hub_client_rejects_non_http_base_url():
    with pytest.raises(SkillRuntimeError, match="source_unavailable"):
        DataHubClient("file:///tmp/key", "secret")


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "credential_invalid"), (402, "source_unavailable"), (403, "source_unavailable"), (422, "source_unavailable")],
)
def test_data_hub_client_maps_http_errors(status: int, code: str):
    def transport(url, headers, timeout):
        return status, b'{"detail":"denied"}'

    client = DataHubClient("https://data.sigmx.cn", "secret", transport=transport)
    with pytest.raises(SkillRuntimeError) as raised:
        client.fetch(DataRequest("stocks.daily", {}))
    assert raised.value.code == code


def test_data_hub_client_requires_credentials():
    with pytest.raises(SkillRuntimeError) as raised:
        DataHubClient("https://data.sigmx.cn", "")
    assert raised.value.code == "credential_missing"
