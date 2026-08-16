from pathlib import Path
import json
import subprocess
import sys

from src.product.architecture_verifier import (
    EvidenceStatus,
    Requirement,
    audit_requirement,
    load_requirements,
)


def test_marks_requirement_missing_when_no_evidence_is_declared(tmp_path: Path) -> None:
    requirement = Requirement(id="3.1", title="Web public discovery", evidence=())

    result = audit_requirement(requirement, tmp_path)

    assert result.status is EvidenceStatus.MISSING
    assert result.reason == "no evidence declared"


def test_rejects_file_existence_as_indirect_product_evidence(tmp_path: Path) -> None:
    implementation = tmp_path / "frontend" / "src" / "Page.tsx"
    implementation.parent.mkdir(parents=True)
    implementation.write_text("export function Page() { return null }", encoding="utf-8")
    requirement = Requirement(
        id="3.2",
        title="Complete instrument page",
        evidence=(f"file:{implementation.relative_to(tmp_path).as_posix()}",),
    )

    result = audit_requirement(requirement, tmp_path)

    assert result.status is EvidenceStatus.INDIRECT
    assert result.reason == "only implementation-file evidence exists"


def test_marks_requirement_complete_only_with_runtime_and_test_evidence(tmp_path: Path) -> None:
    test_file = tmp_path / "agent" / "tests" / "test_feature.py"
    runtime_file = tmp_path / "artifacts" / "feature-smoke.json"
    test_file.parent.mkdir(parents=True)
    runtime_file.parent.mkdir(parents=True)
    test_file.write_text("def test_feature(): pass", encoding="utf-8")
    runtime_file.write_text('{"ok": true}', encoding="utf-8")
    requirement = Requirement(
        id="5.2",
        title="Authoritative Harness Run",
        evidence=(
            f"test:{test_file.relative_to(tmp_path).as_posix()}",
            f"runtime:{runtime_file.relative_to(tmp_path).as_posix()}",
        ),
    )

    result = audit_requirement(requirement, tmp_path)

    assert result.status is EvidenceStatus.COMPLETE
    assert result.reason == "test and runtime evidence exist"


def test_load_requirements_rejects_duplicate_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.json"
    manifest.write_text(
        '[{"id":"3.1","title":"first","evidence":[]},'
        '{"id":"3.1","title":"second","evidence":[]}]',
        encoding="utf-8",
    )

    try:
        load_requirements(manifest)
    except ValueError as exc:
        assert str(exc) == "duplicate requirement id: 3.1"
    else:
        raise AssertionError("duplicate requirement IDs must be rejected")


def test_cli_exits_nonzero_and_reports_incomplete_requirements(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.json"
    manifest.write_text(
        json.dumps([{"id": "3.1", "title": "Web discovery", "evidence": []}]),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[2] / "scripts" / "verify_product_architecture.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--manifest", str(manifest), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "complete": 0,
        "indirect": 0,
        "missing": 1,
        "requirements": [
            {"id": "3.1", "title": "Web discovery", "status": "missing", "reason": "no evidence declared"}
        ],
    }
