from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.product.datahub_credentials import (
    CredentialExpired,
    CredentialIpNotAllowed,
    CredentialLimitReached,
    CredentialNotFound,
    CredentialRevoked,
    DataHubCredentialService,
)
from src.product.store import ProductStore


@pytest.fixture
def service(tmp_path: Path) -> DataHubCredentialService:
    return DataHubCredentialService(ProductStore(tmp_path / "product.db"))


def test_create_returns_plaintext_once_and_store_never_persists_it(
    service: DataHubCredentialService,
) -> None:
    created = service.create("u1", "研究脚本", ["market.v1"], [], None)
    assert re.fullmatch(r"sxd_live_[0-9a-f]{48}", created.plaintext)
    row = service.store._get_conn().execute(
        "SELECT * FROM datahub_credentials WHERE id = ?", (created.id,)
    ).fetchone()
    assert created.plaintext not in "|".join(str(value) for value in row)
    listed = service.list("u1")
    assert listed[0].key_prefix == created.key_prefix
    assert not hasattr(listed[0], "plaintext")
    assert not hasattr(listed[0], "key_hash")


def test_authenticate_returns_personal_principal(service: DataHubCredentialService) -> None:
    created = service.create(
        "u1", "行情", ["stocks.daily", "group:market.v1"], [], None
    )
    principal = service.authenticate(created.plaintext, "203.0.113.8")
    assert principal.user_id == "u1"
    assert principal.credential_id == created.id
    assert principal.scopes == ("group:market.v1", "stocks.daily")


def test_credentials_are_owner_isolated(service: DataHubCredentialService) -> None:
    created = service.create("u1", "私有", ["health"], [], None)
    assert service.list("u2") == []
    with pytest.raises(CredentialNotFound):
        service.revoke("u2", created.id)


def test_revoke_takes_effect_immediately(service: DataHubCredentialService) -> None:
    created = service.create("u1", "临时", ["health"], [], None)
    service.revoke("u1", created.id)
    with pytest.raises(CredentialRevoked):
        service.authenticate(created.plaintext, "203.0.113.8")


def test_expired_key_is_rejected(service: DataHubCredentialService) -> None:
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    created = service.create("u1", "短期", ["health"], [], expiry)
    with pytest.raises(CredentialExpired):
        service.authenticate(
            created.plaintext,
            "203.0.113.8",
            now=datetime.now(timezone.utc) + timedelta(minutes=2),
        )


def test_ip_allowlist_supports_exact_ip_and_cidr(service: DataHubCredentialService) -> None:
    created = service.create(
        "u1", "限定", ["health"], ["203.0.113.8", "198.51.100.0/24"], None
    )
    assert service.authenticate(created.plaintext, "203.0.113.8").user_id == "u1"
    assert service.authenticate(created.plaintext, "198.51.100.9").user_id == "u1"
    with pytest.raises(CredentialIpNotAllowed):
        service.authenticate(created.plaintext, "192.0.2.1")


def test_rotation_revokes_old_key_and_returns_new_secret(
    service: DataHubCredentialService,
) -> None:
    old = service.create("u1", "轮换", ["health"], [], None)
    new = service.rotate("u1", old.id)
    assert new.id != old.id
    assert new.plaintext != old.plaintext
    with pytest.raises(CredentialRevoked):
        service.authenticate(old.plaintext, "203.0.113.8")
    assert service.authenticate(new.plaintext, "203.0.113.8").user_id == "u1"


def test_at_most_ten_active_credentials(service: DataHubCredentialService) -> None:
    for index in range(10):
        service.create("u1", f"Key {index}", ["health"], [], None)
    with pytest.raises(CredentialLimitReached):
        service.create("u1", "Key 10", ["health"], [], None)


@pytest.mark.parametrize(
    ("name", "scopes", "ips", "expiry"),
    [
        ("", ["health"], [], None),
        ("x" * 129, ["health"], [], None),
        ("ok", [], [], None),
        ("ok", ["bad scope"], [], None),
        ("ok", ["health"], ["not-an-ip"], None),
        ("ok", ["health"], [], "2026-08-15"),
    ],
)
def test_create_validates_configuration(
    service: DataHubCredentialService,
    name: str,
    scopes: list[str],
    ips: list[str],
    expiry: str | None,
) -> None:
    with pytest.raises(ValueError):
        service.create("u1", name, scopes, ips, expiry)
