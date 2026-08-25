from __future__ import annotations

import argparse
import json
import os

from .client import DataHubClient, SkillRuntimeError
from .models import DataRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sigmx-skill-data")
    parser.add_argument("capability")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args(argv)
    try:
        params = json.loads(args.params)
        result = DataHubClient(
            os.getenv("SIGMX_DATA_HUB_BASE_URL", "https://data.sigmx.cn"),
            os.getenv("SIGMX_DATA_HUB_KEY", ""),
        ).fetch(DataRequest(args.capability, params, allow_fallback=False))
    except (json.JSONDecodeError, SkillRuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "data": list(result.rows), "source": result.source, "as_of": result.as_of}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
