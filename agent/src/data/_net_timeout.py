"""强制为所有 requests 出站请求注入默认 connect/read timeout。

为什么需要它
------------
akshare 1.18.64 的绝大多数函数（stock_zh_index_daily_em / stock_individual_fund_flow /
stock_zt_pool_em 等）既不接受 ``timeout`` 参数，底层又用裸 ``requests.get(...)``
（无 timeout）。当上游（东财/新浪）TCP 建连卡在 SYN_SENT 或 socket recv 永久阻塞时，
调用方会**无限挂起** —— 这曾导致 ``once`` 全量回补卡死 43 分钟、deadline 形同虚设。

requests 的所有请求最终都经过 ``requests.adapters.HTTPAdapter.send``，它是唯一的公共
瓶颈。在这里兜底注入默认 timeout，可一次性覆盖：

* akshare 全部 1125 处裸 ``requests.get``（含未来新增函数）
* 项目内其他未显式传 timeout 的 ``requests.get``

已显式传入 timeout 的调用（如 ``astock_client.em_get`` 的 ``timeout=15``）不受影响 ——
patch 只在调用方未传 timeout（None）时注入。

可配置（环境变量）
------------------
* ``MARKET_SYNC_NET_TIMEOUT``        默认 ``1``（开启）。设 ``0`` 关闭 patch。
* ``MARKET_SYNC_NET_TIMEOUT_CONNECT`` 默认 ``5``（秒，建连阶段）。
* ``MARKET_SYNC_NET_TIMEOUT_READ``    默认 ``30``（秒，两次 read 之间）。

跨平台说明
----------
timeout 在 socket 层生效，**Windows / Linux 均有效**（不依赖 POSIX-only 的
``signal.SIGALRM``）。这对本项目的 win32 部署至关重要。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_patched = False


def install() -> None:
    """Idempotently monkey-patch ``HTTPAdapter.send`` to inject a default timeout.

    Safe to call multiple times — only patches once. No-op if
    ``MARKET_SYNC_NET_TIMEOUT=0``.
    """
    global _patched
    if _patched:
        return
    if os.getenv("MARKET_SYNC_NET_TIMEOUT", "1") == "0":
        _patched = True  # mark as resolved so we don't keep re-checking env
        logger.info("net_timeout: disabled via MARKET_SYNC_NET_TIMEOUT=0")
        return

    # Lazy import so importing this module has zero side effects.
    from requests.adapters import HTTPAdapter

    connect = float(os.getenv("MARKET_SYNC_NET_TIMEOUT_CONNECT", "5"))
    read = float(os.getenv("MARKET_SYNC_NET_TIMEOUT_READ", "30"))
    default_timeout = (connect, read)

    original_send = HTTPAdapter.send

    def patched_send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = default_timeout
        return original_send(self, request, **kwargs)

    HTTPAdapter.send = patched_send  # type: ignore[method-assign]
    _patched = True
    logger.info(
        "net_timeout: patched HTTPAdapter.send default timeout=(connect=%ss, read=%ss)",
        connect,
        read,
    )
