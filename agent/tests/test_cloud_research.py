from __future__ import annotations

from pathlib import Path

import pytest

from src.product.cloud_research import CloudResearchService, ReportRevoked
from src.product.store import ProductStore


@pytest.fixture
def cloud(tmp_path: Path) -> CloudResearchService:
    return CloudResearchService(ProductStore(tmp_path / "product.db"))


def test_saved_queries_are_personal_and_keep_latest_first(cloud: CloudResearchService) -> None:
    first = cloud.save_query("u1", "低估值高股息", {"matches": 8})
    second = cloud.save_query("u1", "新能源成交放量", {"matches": 3})
    cloud.save_query("u2", "另一用户", {"matches": 1})

    assert [item.id for item in cloud.list_saved_queries("u1")] == [second.id, first.id]
    assert all(item.user_id == "u1" for item in cloud.list_saved_queries("u1"))


def test_watchlist_is_unique_per_user_and_owner_isolated(cloud: CloudResearchService) -> None:
    cloud.add_watchlist("u1", "600519.SH", "贵州茅台")
    cloud.add_watchlist("u1", "600519.SH", "贵州茅台")
    cloud.add_watchlist("u2", "600519.SH", "贵州茅台")

    assert [item.symbol for item in cloud.list_watchlist("u1")] == ["600519.SH"]
    assert cloud.remove_watchlist("u2", "600519.SH") is True
    assert [item.symbol for item in cloud.list_watchlist("u1")] == ["600519.SH"]


def test_report_snapshot_is_immutable_and_revocation_is_explicit(cloud: CloudResearchService) -> None:
    report = cloud.publish_report("u1", "贵州茅台简析", "只包含用户确认公开的脱敏摘要")
    public = cloud.get_public_report(report.slug)
    assert public.summary == "只包含用户确认公开的脱敏摘要"
    assert cloud.revoke_report("u2", report.id) is False
    assert cloud.revoke_report("u1", report.id) is True

    with pytest.raises(ReportRevoked):
        cloud.get_public_report(report.slug)


def test_schema_v7_is_recorded(cloud: CloudResearchService) -> None:
    versions = {
        row[0]
        for row in cloud.store._get_conn().execute("SELECT version FROM product_migrations")
    }
    assert 7 in versions


def test_publish_report_rejects_advisory_content(cloud: CloudResearchService) -> None:
    """发布 gate：建议类表述拒绝发布，命中清单回给调用方（不静默改写）。"""
    with pytest.raises(ValueError, match="合规检查"):
        cloud.publish_report("u1", "荐股帖", "该股强势，建议立即建仓并设目标价 88 元。")

    # 变形逃逸也拦得住（全角/插分隔）
    with pytest.raises(ValueError):
        cloud.publish_report("u1", "变形", "可以考虑立即建·仓。")


def test_publish_report_accepts_neutral_statements(cloud: CloudResearchService) -> None:
    report = cloud.publish_report("u1", "中性复盘", "本日涨停 58 家，跌停 6 家，情绪分 62.0。")
    assert cloud.get_public_report(report.slug).summary.startswith("本日涨停 58 家")
