"""Personal Data Hub credential lifecycle and authentication."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.product.store import ProductStore


_SCOPE_RE = re.compile(r"^(?:group:)?[a-z][a-z0-9_.-]{0,127}$")


class CredentialNotFound(Exception):
    pass


class CredentialRevoked(Exception):
    pass


class CredentialExpired(Exception):
    pass


class CredentialIpNotAllowed(Exception):
    pass


class CredentialLimitReached(Exception):
    pass


@dataclass(frozen=True)
class CreatedCredential:
    id: str
    plaintext: str
    key_prefix: str
    name: str
    scopes: tuple[str, ...]
    ip_allowlist: tuple[str, ...]
    expires_at: str | None
    created_at: str


@dataclass(frozen=True)
class CredentialView:
    id: str
    key_prefix: str
    name: str
    scopes: tuple[str, ...]
    ip_allowlist: tuple[str, ...]
    expires_at: str | None
    last_used_at: str | None
    created_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class CredentialPrincipal:
    credential_id: str
    user_id: str
    key_prefix: str
    scopes: tuple[str, ...]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataHubCredentialService:
    def __init__(
        self, store: ProductStore, now: Callable[[], datetime] = _utc_now
    ) -> None:
        self.store = store
        self._now = now

    def create(
        self,
        user_id: str,
        name: str,
        scopes: list[str],
        ip_allowlist: list[str],
        expires_at: str | None,
    ) -> CreatedCredential:
        config = self._validate(name, scopes, ip_allowlist, expires_at)
        with self.store.transaction() as conn:
            return self._insert(conn, user_id, *config)

    def list(self, user_id: str) -> list[CredentialView]:
        rows = self.store._get_conn().execute(
            "SELECT id, key_prefix, name, scopes_json, ip_allowlist_json, expires_at, "
            "last_used_at, created_at, revoked_at FROM datahub_credentials "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        return [self._view(row) for row in rows]

    def authenticate(
        self, plaintext: str, remote_ip: str, *, now: datetime | None = None
    ) -> CredentialPrincipal:
        if not re.fullmatch(r"sxd_live_[0-9a-f]{48}", plaintext or ""):
            raise CredentialNotFound("credential not found")
        digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM datahub_credentials WHERE key_hash = ?", (digest,)
            ).fetchone()
            if row is None or not hmac.compare_digest(row["key_hash"], digest):
                raise CredentialNotFound("credential not found")
            if row["revoked_at"] is not None:
                raise CredentialRevoked("credential has been revoked")
            current = now or self._now()
            if row["expires_at"] is not None and datetime.fromisoformat(row["expires_at"]) <= current:
                raise CredentialExpired("credential has expired")
            self._check_ip(json.loads(row["ip_allowlist_json"]), remote_ip)
            conn.execute(
                "UPDATE datahub_credentials SET last_used_at = ? WHERE id = ?",
                (current.isoformat(), row["id"]),
            )
            return CredentialPrincipal(
                credential_id=row["id"],
                user_id=row["user_id"],
                key_prefix=row["key_prefix"],
                scopes=tuple(json.loads(row["scopes_json"])),
            )

    def revoke(self, user_id: str, credential_id: str) -> None:
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM datahub_credentials WHERE id = ? AND user_id = ?",
                (credential_id, user_id),
            ).fetchone()
            if row is None:
                raise CredentialNotFound(credential_id)
            if row["revoked_at"] is None:
                conn.execute(
                    "UPDATE datahub_credentials SET revoked_at = ? WHERE id = ?",
                    (self._now().isoformat(), credential_id),
                )

    def rotate(self, user_id: str, credential_id: str) -> CreatedCredential:
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM datahub_credentials WHERE id = ? AND user_id = ?",
                (credential_id, user_id),
            ).fetchone()
            if row is None:
                raise CredentialNotFound(credential_id)
            if row["revoked_at"] is not None:
                raise CredentialRevoked(credential_id)
            conn.execute(
                "UPDATE datahub_credentials SET revoked_at = ? WHERE id = ?",
                (self._now().isoformat(), credential_id),
            )
            return self._insert(
                conn,
                user_id,
                row["name"],
                tuple(json.loads(row["scopes_json"])),
                tuple(json.loads(row["ip_allowlist_json"])),
                row["expires_at"],
            )

    def _insert(self, conn, user_id, name, scopes, ip_allowlist, expires_at) -> CreatedCredential:
        active = conn.execute(
            "SELECT COUNT(*) FROM datahub_credentials WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,),
        ).fetchone()[0]
        if active >= 10:
            raise CredentialLimitReached("at most 10 active credentials are allowed")
        plaintext = "sxd_live_" + secrets.token_hex(24)
        credential_id = uuid.uuid4().hex
        created_at = self._now().isoformat()
        key_prefix = plaintext[:20]
        conn.execute(
            "INSERT INTO datahub_credentials "
            "(id, user_id, name, key_hash, key_prefix, scopes_json, ip_allowlist_json, "
            "expires_at, last_used_at, created_at, revoked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)",
            (
                credential_id,
                user_id,
                name,
                hashlib.sha256(plaintext.encode("utf-8")).hexdigest(),
                key_prefix,
                json.dumps(scopes, ensure_ascii=False),
                json.dumps(ip_allowlist, ensure_ascii=False),
                expires_at,
                created_at,
            ),
        )
        return CreatedCredential(
            credential_id, plaintext, key_prefix, name, scopes, ip_allowlist, expires_at, created_at
        )

    @staticmethod
    def _validate(name, scopes, ip_allowlist, expires_at):
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 128:
            raise ValueError("name must contain 1 to 128 characters")
        clean_scopes = tuple(sorted(set(scopes)))
        if not clean_scopes or any(not _SCOPE_RE.fullmatch(scope) for scope in clean_scopes):
            raise ValueError("invalid credential scope")
        clean_ips: list[str] = []
        for value in ip_allowlist:
            try:
                if "/" in value:
                    clean_ips.append(str(ipaddress.ip_network(value, strict=True)))
                else:
                    clean_ips.append(str(ipaddress.ip_address(value)))
            except ValueError as exc:
                raise ValueError("invalid IP allowlist entry") from exc
        clean_expiry = None
        if expires_at is not None:
            try:
                parsed = datetime.fromisoformat(expires_at)
            except ValueError as exc:
                raise ValueError("expires_at must be an ISO datetime") from exc
            if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
                raise ValueError("expires_at must use UTC timezone")
            clean_expiry = parsed.isoformat()
        return clean_name, clean_scopes, tuple(sorted(set(clean_ips))), clean_expiry

    @staticmethod
    def _check_ip(allowlist: list[str], remote_ip: str) -> None:
        if not allowlist:
            return
        try:
            address = ipaddress.ip_address(remote_ip)
        except ValueError as exc:
            raise CredentialIpNotAllowed("remote IP is invalid") from exc
        for allowed in allowlist:
            if "/" in allowed and address in ipaddress.ip_network(allowed):
                return
            if "/" not in allowed and address == ipaddress.ip_address(allowed):
                return
        raise CredentialIpNotAllowed("remote IP is not allowed")

    @staticmethod
    def _view(row) -> CredentialView:
        return CredentialView(
            id=row["id"],
            key_prefix=row["key_prefix"],
            name=row["name"],
            scopes=tuple(json.loads(row["scopes_json"])),
            ip_allowlist=tuple(json.loads(row["ip_allowlist_json"])),
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
        )
