"""Data Hub 读侧一致性：路由 ↔ 计费目录 ↔ 文档 三方不再漂移。

同一份端点清单曾经手抄 4 处（路由装饰器 / datahub_catalog._V1 /
_sigmx_endpoint_list / docs 表格），任何一处落后都无人发现。本文件把
三方的交由测试钉死：目录里的每个端点必须有真实路由、必须出现在
health 清单里、必须写进 docs/datahub-api.md。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import FastAPI

from src.api.sigmx_routes import _sigmx_endpoint_list, register_sigmx_routes
from src.product.datahub_catalog import ENDPOINT_CATALOG_V2

_DOCS = Path(__file__).resolve().parents[2] / "docs" / "datahub-api.md"


def _catalog_paths() -> dict[str, str]:
    """endpoint_code → path（v2 目录当前有效端点）。"""
    return {
        entry.endpoint_code: entry.path_pattern
        for entry in ENDPOINT_CATALOG_V2
        if entry.enabled
    }


@pytest.fixture(scope="module")
def app_routes() -> set[str]:
    app = FastAPI()
    register_sigmx_routes(app)
    return {getattr(route, "path", "") for route in app.routes}


def test_every_catalog_endpoint_has_a_registered_route(app_routes):
    """目录（计费口径）里的每个端点都必须是真实注册的 GET 路由。"""
    missing = [
        (code, path)
        for code, path in sorted(_catalog_paths().items())
        if path not in app_routes
    ]
    assert not missing, f"catalog 端点没有对应路由: {missing}"


def test_health_endpoint_list_equals_catalog_minus_health():
    """health 回显清单 = 目录去掉 health 自身（派生后天然同源）。"""
    expected = sorted(
        path for path in _catalog_paths().values() if path != "/api/v1/health"
    )
    assert _sigmx_endpoint_list() == expected


def test_registered_sigmx_routes_all_in_catalog(app_routes):
    """反向：凡是 /api/v1/ 下 sigmx 路由都在目录里（消灭"路由上了、目录没上"）。"""
    catalog = set(_catalog_paths().values())
    uncataloged = sorted(
        path
        for path in app_routes
        if path.startswith("/api/v1/") and path not in catalog
    )
    assert not uncataloged, f"路由未入计费目录: {uncataloged}"


def test_docs_cover_every_catalog_endpoint():
    """docs/datahub-api.md 必须写到每个端点（文档不再烂尾）。"""
    import re

    doc = _DOCS.read_text(encoding="utf-8")
    missing = []
    for code, path in sorted(_catalog_paths().items()):
        # 文档省略 /api/v1 前缀（Base 在头部声明），以反引号 `GET /xxx` 书写；
        # 「市场总览」节把参数写进同一反引号（`GET /xxx?a`），其余节参数另列。
        short = path.removeprefix("/api/v1")
        pattern = re.compile(r"`GET " + re.escape(short) + r"(?:`|\?)")
        if not pattern.search(doc):
            missing.append((code, short))
    assert not missing, f"docs/datahub-api.md 缺少端点条目: {missing}"
