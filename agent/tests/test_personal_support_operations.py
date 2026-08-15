import json

import pytest

from src.product.store import ProductStore
from src.product.support_operations import PersonalSupportOperations, SupportTargetNotFound


def test_compensation_is_positive_separate_and_audited(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    service = PersonalSupportOperations(store)
    service.compensate("admin-1", "user-1", "research", 25, "任务异常补偿")
    service.compensate("admin-1", "user-1", "data", 100, "数据调用异常补偿")
    conn = store._get_conn()
    assert conn.execute("SELECT SUM(amount_remaining) n FROM credit_lots WHERE user_id='user-1'").fetchone()["n"] == 25
    assert conn.execute("SELECT SUM(amount_remaining) n FROM data_credit_lots WHERE owner_id='user-1'").fetchone()["n"] == 100
    audits = conn.execute("SELECT * FROM audit_log ORDER BY created_at").fetchall()
    assert len(audits) == 2
    assert json.loads(audits[0]["metadata_json"])["ledger"] == "research"
    with pytest.raises(ValueError):
        service.compensate("admin-1", "user-1", "research", -1, "非法扣减测试")


def test_security_revocations_are_owner_scoped_and_audited(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    conn = store._get_conn()
    conn.execute("INSERT INTO devices (id,user_id,name,fingerprint_hash,created_at,revoked_at) VALUES ('d1','u1','PC','fp','2026-08-16',NULL)")
    conn.execute("INSERT INTO datahub_credentials (id,user_id,name,key_hash,key_prefix,scopes_json,ip_allowlist_json,created_at,credential_kind) VALUES ('k1','u1','Key','hash','sxd','[]','[]','2026-08-16','personal')")
    conn.commit()
    service = PersonalSupportOperations(store)
    with pytest.raises(SupportTargetNotFound):
        service.revoke_device("admin", "u2", "d1", "用户请求解绑")
    service.revoke_device("admin", "u1", "d1", "用户请求解绑")
    service.revoke_credential("admin", "u1", "k1", "密钥疑似泄露")
    assert conn.execute("SELECT revoked_at FROM devices WHERE id='d1'").fetchone()["revoked_at"]
    assert conn.execute("SELECT revoked_at FROM datahub_credentials WHERE id='k1'").fetchone()["revoked_at"]
    assert conn.execute("SELECT COUNT(*) n FROM audit_log").fetchone()["n"] == 2
