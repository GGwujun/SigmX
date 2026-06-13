"""Send messages to Feishu / DingTalk / WeChat group robots.

Each platform accepts a markdown-ish text payload. Feishu and DingTalk support
HMAC signing (secret); WeChat group robots use a key in the webhook URL only.

All senders return (ok, message). They never raise — network/parse failures
are reported as ok=False with the error string, so the API layer can relay it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Any

import requests

from src.notify.models import PlatformConfig

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> tuple[bool, str]:
    try:
        resp = requests.post(url, json=payload, headers=headers or {}, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        return False, f"请求失败: {exc}"
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    # Platforms return JSON with an errcode/code field; 0 = success.
    try:
        data = resp.json()
    except ValueError:
        return True, "已发送（无响应体）"
    # Feishu: {"code":0,"msg":"success"} or {"StatusCode":0}
    # DingTalk: {"errcode":0,"errmsg":"ok"}
    # WeChat:  {"errcode":0,"errmsg":"ok"}
    errcode = data.get("code", data.get("StatusCode", data.get("errcode", 0)))
    if errcode in (0, None):
        return True, data.get("msg") or data.get("errmsg") or "发送成功"
    return False, f"平台返回错误 {errcode}: {data.get('msg') or data.get('errmsg') or resp.text[:200]}"


# ------------------------------------------------------------------ feishu

def _feishu_sign(secret: str, timestamp: int) -> str:
    """Feishu signature: base64(hmac_sha256(timestamp + '\n' + secret, ''))."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu(cfg: PlatformConfig, title: str, markdown: str) -> tuple[bool, str]:
    if not cfg.webhook_url:
        return False, "未配置 Webhook"
    timestamp = int(time.time())
    payload: dict[str, Any] = {
        "timestamp": str(timestamp),
        "msg_type": "text",
        "content": {"text": f"{title}\n\n{markdown}"},
    }
    if cfg.secret:
        payload["sign"] = _feishu_sign(cfg.secret, timestamp)
    return _post_json(cfg.webhook_url, payload)


# ------------------------------------------------------------------ dingtalk

def _dingtalk_sign(secret: str, timestamp: int) -> tuple[str, str]:
    """DingTalk signature returns (sign, full_url_query_suffix)."""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return sign, f"&timestamp={timestamp}&sign={sign}"


def send_dingtalk(cfg: PlatformConfig, title: str, markdown: str) -> tuple[bool, str]:
    if not cfg.webhook_url:
        return False, "未配置 Webhook"
    url = cfg.webhook_url
    if cfg.secret:
        ts = int(round(time.time() * 1000))
        sign, suffix = _dingtalk_sign(cfg.secret, ts)
        url = f"{url}{'&' if '?' in url else '?'}{suffix[1:]}"  # strip leading '&'
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": f"## {title}\n\n{markdown}"},
    }
    return _post_json(url, payload)


# ------------------------------------------------------------------ wechat

def send_wechat(cfg: PlatformConfig, title: str, markdown: str) -> tuple[bool, str]:
    """WeChat Work group robot. Markdown supported."""
    if not cfg.webhook_url:
        return False, "未配置 Webhook"
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": f"## {title}\n\n{markdown}"},
    }
    return _post_json(cfg.webhook_url, payload)


# ------------------------------------------------------------------ dispatch

_SENDERS = {
    "feishu": send_feishu,
    "dingtalk": send_dingtalk,
    "wechat": send_wechat,
}


def send(platform: str, cfg: PlatformConfig, title: str, markdown: str) -> tuple[bool, str]:
    sender = _SENDERS.get(platform.strip().lower())
    if sender is None:
        return False, f"不支持的平台: {platform}"
    return sender(cfg, title, markdown)
