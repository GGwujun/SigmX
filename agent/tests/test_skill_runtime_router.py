import pytest

from src.skill_runtime.client import SkillRuntimeError
from src.skill_runtime.models import DataRequest, DataResult, SkillDataPolicy
from src.skill_runtime.router import SkillDataRouter


class Source:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def fetch(self, request):
        if self.error:
            raise self.error
        return self.result


def policy(*, fallback=("akshare",)):
    return SkillDataPolicy(1, "official", "executable", "data_hub", ("stocks.daily",), fallback, ("CN_A",), ("SIGMX_DATA_HUB_KEY",))


def test_router_uses_data_hub_as_primary_source():
    primary = DataResult(({"code": "000001.SZ"},), "sigmx_data_hub", "stocks.daily", "2026-08-25")
    fallback = Source(DataResult(({"code": "fallback"},), "akshare", None, "2026-08-25"))
    router = SkillDataRouter(Source(primary), {"akshare": fallback})

    assert router.fetch(policy(), DataRequest("stocks.daily", {})) == primary


def test_router_preserves_fallback_provenance_when_primary_unavailable():
    router = SkillDataRouter(
        Source(error=SkillRuntimeError("credential_missing", "missing")),
        {"akshare": Source(DataResult(({"code": "000001.SZ"},), "akshare", None, "2026-08-25"))},
    )

    result = router.fetch(policy(), DataRequest("stocks.daily", {}, allow_fallback=True))

    assert result.source == "akshare"
    assert result.degraded is True
    assert result.degradation_reason == "credential_missing"


def test_router_does_not_fallback_when_request_forbids_it():
    router = SkillDataRouter(Source(error=SkillRuntimeError("credential_missing", "missing")), {})
    with pytest.raises(SkillRuntimeError) as raised:
        router.fetch(policy(), DataRequest("stocks.daily", {}, allow_fallback=False))
    assert raised.value.code == "fallback_not_allowed"


def test_router_rejects_unregistered_fallback_adapter():
    router = SkillDataRouter(Source(error=SkillRuntimeError("source_unavailable", "down")), {})
    with pytest.raises(SkillRuntimeError) as raised:
        router.fetch(policy(fallback=("akshare",)), DataRequest("stocks.daily", {}))
    assert raised.value.code == "source_unavailable"


def test_router_rejects_fallback_schema_mismatch():
    router = SkillDataRouter(
        Source(error=SkillRuntimeError("source_unavailable", "down")),
        {"akshare": Source(DataResult(({"symbol": "000001"},), "akshare", None, "2026-08-25"))},
    )
    with pytest.raises(SkillRuntimeError) as raised:
        router.fetch(policy(), DataRequest("stocks.daily", {}, required_fields=("code",)))
    assert raised.value.code == "fallback_schema_mismatch"
