from __future__ import annotations

import argparse
import json
import os
from typing import Sequence, Type

from .client import DataHubClient, DataHubError


def main(argv: Sequence[str] | None = None, *, client_cls: Type[DataHubClient] = DataHubClient) -> int:
    parser = argparse.ArgumentParser(prog="sigmx-data", description="SigmX Data Hub personal CLI")
    parser.add_argument("--base-url", default=os.getenv("SIGMX_DATAHUB_URL", "https://data.sigmx.cn"))
    sub = parser.add_subparsers(dest="command", required=True)
    get = sub.add_parser("get")
    get.add_argument("path")
    get.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)
    credential = os.getenv("SIGMX_DATAHUB_KEY", "")
    if not credential:
        parser.error("SIGMX_DATAHUB_KEY is required")
    params: dict[str, str] = {}
    for item in args.param:
        if "=" not in item:
            parser.error(f"invalid --param {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        params[key] = value
    try:
        result = client_cls(credential, base_url=args.base_url).get(args.path, params)
    except DataHubError as exc:
        print(json.dumps({"error": str(exc), "status": exc.status, "request_id": exc.request_id}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "data": result.data,
        "meta": {
            "request_id": result.request_id,
            "credits_charged": result.credits_charged,
            "credits_remaining": result.credits_remaining,
        },
    }, ensure_ascii=False, indent=2))
    return 0


def entrypoint() -> None:
    raise SystemExit(main())
