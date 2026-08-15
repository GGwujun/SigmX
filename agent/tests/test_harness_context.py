from __future__ import annotations

import json
from pathlib import Path

from src.harness.context import build_context_manifest


def test_context_manifest_keeps_private_files_local_and_omits_secrets(tmp_path: Path) -> None:
    private = tmp_path / "private-position-notes.txt"
    private.write_text("broker password=super-secret and private holdings", encoding="utf-8")
    manifest = build_context_manifest(
        current_symbol="600519.SH",
        cloud_watchlist_refs=["600519.SH"],
        risk_profile_ref="balanced-v2",
        market_snapshot_ref="market:20260815",
        local_files=[private],
        extra={"api_key": "sxd_live_secret", "theme": "quality"},
    )
    dumped = json.dumps(manifest.to_dict(), ensure_ascii=False)
    assert manifest.local_files[0].local_only is True
    assert manifest.local_files[0].name == private.name
    assert str(private) not in dumped
    assert "super-secret" not in dumped
    assert "sxd_live_secret" not in dumped
    assert manifest.safe_attributes == {"theme": "quality"}


def test_context_manifest_contains_reproducible_public_references() -> None:
    manifest = build_context_manifest(
        current_symbol="000001.SZ", cloud_watchlist_refs=["000001.SZ"],
        risk_profile_ref=None, market_snapshot_ref="market:v42", local_files=[], extra={},
    )
    assert manifest.current_symbol == "000001.SZ"
    assert manifest.market_snapshot_ref == "market:v42"
