"""Compatibility entry point for the migrated hithink-zhishu-query Skill."""
from __future__ import annotations
import json
import sys
from src.skill_runtime.cli import main as runtime_main

if __name__ == "__main__":
    params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        json.loads(params)
    except json.JSONDecodeError:
        params = json.dumps({"query": params}, ensure_ascii=False)
    raise SystemExit(runtime_main(["indices.daily", "--params", params]))
