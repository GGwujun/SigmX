#!/usr/bin/env python3
"""Audit direct completion evidence for the SigmX product architecture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = REPOSITORY_ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.product.architecture_verifier import audit_requirement, load_requirements  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "superpowers" / "plans" / "sigmx-product-requirements.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = [audit_requirement(item, args.root) for item in load_requirements(args.manifest)]
    payload = {
        "complete": sum(result.status.value == "complete" for result in results),
        "indirect": sum(result.status.value == "indirect" for result in results),
        "missing": sum(result.status.value == "missing" for result in results),
        "requirements": [
            {
                "id": result.requirement.id,
                "title": result.requirement.title,
                "status": result.status.value,
                "reason": result.reason,
            }
            for result in results
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for result in payload["requirements"]:
            print(f"{result['status'].upper():8} {result['id']:8} {result['title']} — {result['reason']}")
        print(
            f"complete={payload['complete']} indirect={payload['indirect']} missing={payload['missing']}"
        )
    return 0 if payload["indirect"] == 0 and payload["missing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
