from pathlib import Path

import pytest

from src.skill_runtime.manifest import ManifestValidationError, load_skill_manifest
from src.skill_runtime.migration_registry import policy_for_slug


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "src" / "skills"


def test_parser_returns_nested_sigmx_policy(tmp_path: Path):
    manifest = tmp_path / "SKILL.md"
    manifest.write_text(
        """---
name: sample
description: Sample
sigmx:
  schema_version: 1
  ownership: official
  execution: executable
  primary_source: data_hub
  datahub_endpoints:
    - stocks.daily
  fallback_sources:
    - akshare
  markets:
    - CN_A
  credentials:
    - SIGMX_DATA_HUB_KEY
---
# Sample
""",
        encoding="utf-8",
    )

    parsed = load_skill_manifest(manifest)

    assert parsed.slug == "sample"
    assert parsed.policy.ownership == "official"
    assert parsed.policy.datahub_endpoints == ("stocks.daily",)
    assert parsed.policy.fallback_sources == ("akshare",)
    assert parsed.policy.credential_required is True


def test_data_hub_policy_requires_a_cataloged_endpoint(tmp_path: Path):
    manifest = tmp_path / "SKILL.md"
    manifest.write_text(
        """---
name: invalid
sigmx:
  schema_version: 1
  ownership: official
  execution: instructional
  primary_source: data_hub
  datahub_endpoints: []
  fallback_sources: []
  markets: [CN_A]
  credentials: [SIGMX_DATA_HUB_KEY]
---
# Invalid
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestValidationError, match="datahub_endpoints"):
        load_skill_manifest(manifest)


def test_migration_registry_covers_every_installed_skill():
    slugs = sorted(path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md"))

    assert len(slugs) == 102
    assert [slug for slug in slugs if policy_for_slug(slug) is None] == []


@pytest.mark.parametrize(
    "slug",
    [
        "hithink-finance-query",
        "hithink-astock-selector",
        "announcement-search",
        "news-search",
        "report-search",
    ],
)
def test_imported_iwencai_skills_are_adapted_without_iwencai_credentials(slug: str):
    policy = policy_for_slug(slug)

    assert policy is not None
    assert policy.ownership == "adapted"
    assert "IWENCAI_API_KEY" not in policy.credentials
    assert policy.primary_source in {"data_hub", "public_source"}


def test_unknown_fallback_source_is_rejected(tmp_path: Path):
    manifest = tmp_path / "SKILL.md"
    manifest.write_text(
        """---
name: invalid-fallback
sigmx:
  schema_version: 1
  ownership: adapted
  execution: instructional
  primary_source: public_source
  datahub_endpoints: []
  fallback_sources: [mystery-feed]
  markets: [GLOBAL]
  credentials: []
---
# Invalid fallback
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestValidationError, match="fallback"):
        load_skill_manifest(manifest)


@pytest.mark.parametrize(
    ("slug", "primary_source", "market"),
    [
        ("adr-hshare", "public_source", "GLOBAL"),
        ("commodity-analysis", "public_source", "GLOBAL"),
        ("doc-reader", "none", "LOCAL"),
        ("hithink-usstock-selector", "public_source", "US"),
        ("hithink-hkstock-selector", "public_source", "HK"),
    ],
)
def test_non_data_hub_capabilities_are_not_mislabeled_as_data_hub(slug: str, primary_source: str, market: str):
    policy = policy_for_slug(slug)

    assert policy is not None
    assert policy.primary_source == primary_source
    assert market in policy.markets
    assert policy.datahub_endpoints == ()


def test_methodology_ownership_is_distinct_from_third_party_data_adapters():
    assert policy_for_slug("adr-hshare").ownership == "official"
    assert policy_for_slug("commodity-analysis").ownership == "official"
    assert policy_for_slug("akshare").ownership == "third_party"
