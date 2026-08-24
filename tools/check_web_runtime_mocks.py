"""Fail CI when Web production pages contain runtime demo business data."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


DEMO_MARKERS = (
    "演示数据",
    "原型演示",
    "当前演示",
    "source: \"demo\"",
    "source: 'demo'",
)
BUSINESS_ARRAY_NAMES = {
    "articles",
    "candidates",
    "data",
    "filters",
    "items",
    "marketpulse",
    "reports",
    "researchcandidates",
    "researchtopics",
    "rows",
    "skills",
    "stats",
}
ARRAY_PATTERN = re.compile(
    r"\bconst\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*\[\s*\{",
    re.MULTILINE,
)
DERIVED_ARRAY_ALLOWLIST = {
    ("pages/dailyrecommendations.tsx", "rows"),
    ("pages/recommendationhistory.tsx", "rows"),
    ("pages/trackingdashboard.tsx", "items"),
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    reason: str


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_runtime_mocks(root: Path, scope: str | None = None) -> list[Violation]:
    """Return suspicious runtime fixtures while excluding tests and metadata."""
    source_root = root / "frontend" / "src"
    if not source_root.exists():
        return []
    violations: list[Violation] = []
    for path in sorted((*source_root.rglob("*.ts"), *source_root.rglob("*.tsx"))):
        relative = path.relative_to(source_root)
        if "__tests__" in relative.parts or path.name.endswith((".test.ts", ".test.tsx")):
            continue
        normalized = relative.as_posix().lower()
        if scope == "research" and not any(
            token in normalized for token in ("landingpage", "researchresult", "researchworkbench", "researchapi")
        ):
            continue
        text = path.read_text(encoding="utf-8")
        for marker in DEMO_MARKERS:
            start = 0
            while (offset := text.find(marker, start)) >= 0:
                violations.append(Violation(path, _line_number(text, offset), "demo-marker"))
                start = offset + len(marker)
        if "/pages/" in f"/{normalized}":
            for match in ARRAY_PATTERN.finditer(text):
                name = match.group(1).lower()
                if name in BUSINESS_ARRAY_NAMES and (normalized, name) not in DERIVED_ARRAY_ALLOWLIST:
                    violations.append(
                        Violation(path, _line_number(text, match.start()), "page-business-array")
                    )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--scope", choices=("research",), default=None)
    args = parser.parse_args()
    violations = scan_runtime_mocks(args.root.resolve(), args.scope)
    for item in violations:
        print(f"{item.path}:{item.line}: {item.reason}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
