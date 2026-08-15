"""Dependency-free SigmX Data Hub personal client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class DataHubError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.request_id = request_id


@dataclass(frozen=True)
class DataHubResponse:
    data: Any
    status: int
    request_id: str | None
    credits_charged: int
    credits_remaining: int | None


class DataHubClient:
    def __init__(
        self,
        credential: str,
        *,
        base_url: str = "https://data.sigmx.cn",
        timeout: float = 30.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not credential.startswith("sxd_live_") or len(credential) < 14:
            raise ValueError("credential must be an sxd_live_ Data Hub Credential")
        parsed = urlparse(base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ValueError("base_url must use HTTPS (HTTP is allowed only for localhost)")
        self._credential = credential
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> DataHubResponse:
        if not path.startswith("/api/v1/") or "://" in path or ".." in path:
            raise ValueError("path must be an absolute SigmX /api/v1/ path")
        query = urlencode(
            [(key, value) for key, value in (params or {}).items() if value is not None],
            doseq=True,
        )
        url = f"{self.base_url}{path}{'?' + query if query else ''}"
        request = Request(
            url,
            headers={"Authorization": f"Bearer {self._credential}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return DataHubResponse(
                    payload,
                    int(response.status),
                    response.headers.get("X-Request-ID"),
                    int(response.headers.get("X-DataHub-Credits-Charged", "0")),
                    self._optional_int(response.headers.get("X-DataHub-Credits-Remaining")),
                )
        except HTTPError as exc:
            request_id = exc.headers.get("X-Request-ID") if exc.headers else None
            try:
                body = json.loads(exc.read().decode("utf-8"))
                message = body.get("detail") or body.get("message") or f"HTTP {exc.code}"
            except Exception:
                message = f"HTTP {exc.code}"
            raise DataHubError(str(message), status=exc.code, request_id=request_id) from exc
        except (URLError, TimeoutError) as exc:
            raise DataHubError("Data Hub connection failed") from exc

    def health(self) -> DataHubResponse:
        return self.get("/api/v1/health")

    def stocks_daily(self, symbol: str, **params: Any) -> DataHubResponse:
        return self.get("/api/v1/stocks/daily", {"symbol": symbol, **params})

    @staticmethod
    def _optional_int(value: str | None) -> int | None:
        return int(value) if value is not None else None
