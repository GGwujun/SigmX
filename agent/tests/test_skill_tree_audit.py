from pathlib import Path

from src.skill_runtime.manifest import validate_skill_tree


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "src" / "skills"


def test_every_installed_skill_has_a_valid_sigmx_policy():
    manifests = validate_skill_tree(SKILLS_ROOT)

    assert len(manifests) == 102
    assert len({item.slug for item in manifests}) == 102


def test_no_published_skill_defaults_to_iwencai_runtime():
    offenders = []
    for path in SKILLS_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".py"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "openapi.iwencai.com" in content or "IWENCAI_API_KEY" in content:
            offenders.append(str(path.relative_to(SKILLS_ROOT)))

    assert offenders == []


def test_executable_policy_has_a_python_entrypoint():
    offenders = []
    for manifest in validate_skill_tree(SKILLS_ROOT):
        if manifest.policy.execution != "executable":
            continue
        root = SKILLS_ROOT / manifest.slug
        if not any(root.rglob("*.py")):
            offenders.append(manifest.slug)

    assert offenders == []


def test_python_entrypoints_are_disclosed_as_executable():
    offenders = []
    for manifest in validate_skill_tree(SKILLS_ROOT):
        if any((SKILLS_ROOT / manifest.slug).rglob("*.py")) and manifest.policy.execution != "executable":
            offenders.append(manifest.slug)

    assert offenders == []


def test_every_skill_declares_sigmx_policy_as_authoritative_runtime_rule():
    offenders = []
    for manifest in validate_skill_tree(SKILLS_ROOT):
        body = manifest.content.split("---", 2)[-1]
        if "## SigmX 数据运行规则（优先级最高）" not in body:
            offenders.append(manifest.slug)

    assert offenders == []


def test_data_hub_primary_skills_do_not_require_third_party_credentials():
    offenders = []
    for manifest in validate_skill_tree(SKILLS_ROOT):
        if manifest.policy.primary_source != "data_hub":
            continue
        root = SKILLS_ROOT / manifest.slug
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".py"}:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if "TUSHARE_TOKEN" in content or "IWENCAI_API_KEY" in content:
                    offenders.append(str(path.relative_to(SKILLS_ROOT)))

    assert offenders == []
