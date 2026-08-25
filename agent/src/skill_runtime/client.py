from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .models import DataRequest, DataResult
from .registry import endpoint_path


class SkillRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


Transport = Callable[[str, dict[str, str], float], tuple[int, bytes]]


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()
    except URLError as exc:
        raise SkillRuntimeError("source_unavailable", str(exc.reason)) from exc


class DataHubClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0, transport: Transport | None = None):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SkillRuntimeError("source_unavailable", "Data Hub base URL must be HTTP(S)")
        if not api_key:
            raise SkillRuntimeError("credential_missing", "SIGMX_DATA_HUB_KEY is not configured")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport or _default_transport

    def fetch(self, request: DataRequest) -> DataResult:
        try:
            path = endpoint_path(request.capability)
        except KeyError as exc:
            raise SkillRuntimeError("capability_not_supported", str(exc)) from exc
        query = urlencode(request.params, doseq=True)
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        if urlparse(url).netloc != urlparse(self.base_url).netloc:
            raise SkillRuntimeError("source_unavailable", "request escaped configured Data Hub origin")
        status, raw = self.transport(url, {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}, self.timeout)
        if status >= 400:
            code = "credential_invalid" if status == 401 else "source_unavailable"
            raise SkillRuntimeError(code, f"Data Hub returned HTTP {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SkillRuntimeError("source_unavailable", "Data Hub returned invalid JSON") from exc
        data = payload.get("data", payload)
        rows = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        return DataResult(tuple(row for row in rows if isinstance(row, dict)), "sigmx_data_hub", request.capability, meta.get("as_of"))
