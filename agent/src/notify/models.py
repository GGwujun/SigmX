"""Pydantic models for notification config."""

from __future__ import annotations

from pydantic import BaseModel


class PlatformConfig(BaseModel):
    """One platform's config (feishu / dingtalk / wechat)."""
    enabled: bool = False
    webhook_url: str = ""
    secret: str = ""               # sign secret (feishu/dingtalk); unused for wechat
    pre_market_enabled: bool = False
    pre_market_time: str = "08:45"
    after_close_enabled: bool = False
    after_close_time: str = "15:10"
    custom_enabled: bool = False
    custom_time: str = "20:30"


class NotifyConfig(BaseModel):
    feishu: PlatformConfig = PlatformConfig()
    dingtalk: PlatformConfig = PlatformConfig()
    wechat: PlatformConfig = PlatformConfig()


class TestRequest(BaseModel):
    platform: str  # "feishu" | "dingtalk" | "wechat"


class TestResponse(BaseModel):
    ok: bool
    message: str
