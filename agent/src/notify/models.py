"""Pydantic models for notification config."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class NoiseConfigModel(BaseModel):
    """噪声控制配置（去重/冷却/静默/最低严重度）。"""
    dedup_ttl_seconds: int = 0
    cooldown_seconds: int = 0
    quiet_hours: str = ""
    timezone: str = "Asia/Shanghai"
    min_severity: str = ""


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
    noise: NoiseConfigModel = NoiseConfigModel()


class TestRequest(BaseModel):
    platform: str  # "feishu" | "dingtalk" | "wechat"


class TestResponse(BaseModel):
    ok: bool
    message: str
