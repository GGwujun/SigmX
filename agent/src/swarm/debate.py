"""Claim-driven structured debate state machine.

参考 TradingAgents-AShare 的 debate_utils.py，适配 Vibe-Trading 的 DAG Swarm 架构。

辩论流程：
  1. bull_case / bear_case 输出初始 Claim（带 <!-- DEBATE_STATE --> 标记）
  2. bull_rebuttal / bear_rebuttal 逐条反驳对方 Claim
  3. neutral_synthesis 裁决 open/unresolved Claim
  4. 前端通过 SSE 实时看到 Claim 创建/反驳/解决的流转

LLM 输出中的结构化标记格式：
  <!-- DEBATE_STATE: {
    "responded_claim_ids": ["BEAR-1"],
    "new_claims": [{"claim": "...", "evidence": [...], "confidence": 0.7}],
    "resolved_claim_ids": [],
    "unresolved_claim_ids": ["BEAR-2"],
    "round_summary": "..."
  } -->
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────

@dataclass
class Claim:
    """一条辩论 Claim。"""
    claim_id: str               # "BULL-1", "BEAR-1"
    speaker: str                # "多头首席研究员"
    speaker_key: str            # "bull" | "bear" | "neutral"
    stance: str                 # "bullish" | "bearish" | "neutral"
    claim: str                  # 核心论点（≤30字）
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5
    status: str = "open"        # open → addressed → resolved/unresolved
    target_claim_ids: list[str] = field(default_factory=list)
    round_index: int = 1

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "speaker": self.speaker,
            "speaker_key": self.speaker_key,
            "stance": self.stance,
            "claim": self.claim,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
            "status": self.status,
            "target_claim_ids": self.target_claim_ids,
            "round_index": self.round_index,
        }


@dataclass
class DebateState:
    """辩论整体状态。"""
    claims: dict[str, Claim] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    count: int = 0
    focus_claim_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claims": {k: v.to_dict() for k, v in self.claims.items()},
            "history": self.history,
            "count": self.count,
            "focus_claim_ids": self.focus_claim_ids,
        }


# ─────────────────────────────────────────────────────────────────
# HTML 标记解析
# ─────────────────────────────────────────────────────────────────

_DEBATE_RE = re.compile(
    r"<!--\s*DEBATE_STATE:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def parse_debate_payload(text: str) -> tuple[dict | None, str]:
    """从 LLM 输出中提取 DEBATE_STATE JSON 并剥离标记。

    Returns:
        (parsed_dict_or_None, cleaned_text_without_marker)
    """
    match = _DEBATE_RE.search(text)
    if not match:
        return None, text

    raw = match.group(1)
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("debate: failed to parse DEBATE_STATE JSON: %s", raw[:200])
        return None, text

    cleaned = _DEBATE_RE.sub("", text).strip()
    return payload, cleaned


def strip_debate_markers(text: str) -> str:
    """移除所有 DEBATE_STATE 标记，返回纯文本。"""
    return _DEBATE_RE.sub("", text).strip()


# ─────────────────────────────────────────────────────────────────
# 轮次目标
# ─────────────────────────────────────────────────────────────────

INVESTMENT_ROUND_GOALS = [
    "建立最核心的正反方论点，明确多空双方的核心论据和关键证据",
    "优先攻击对手最脆弱的假设，暴露数据缺口和逻辑漏洞",
    "围绕时间窗口与触发条件判断：催化剂是否足够强、何时兑现",
    "围绕失败路径判断：谁低估了风险？止损/止盈是否现实？",
    "检查剩余分歧是否仍有信息增量，准备收口形成概率加权结论",
]

RISK_ROUND_GOALS = [
    "识别交易方案中最可能导致不可逆损失的核心风险",
    "检验止损在 A 股约束下（T+1/涨跌停/流动性）是否真实可执行",
    "评估仓位大小与置信度是否匹配，压力测试极端情景",
    "判断激进方和保守方谁的风险评估更有数据支撑",
    "形成最终风控裁决：通过/降仓通过/否决",
]


def get_round_goal(count: int, domain: str = "investment") -> str:
    """获取当前轮次的辩论目标。"""
    goals = RISK_ROUND_GOALS if domain == "risk" else INVESTMENT_ROUND_GOALS
    idx = min(count, len(goals) - 1)
    return goals[max(0, idx)]


# ─────────────────────────────────────────────────────────────────
# 状态更新
# ─────────────────────────────────────────────────────────────────

def update_debate_state(
    state: DebateState,
    payload: dict,
    speaker: str,
    speaker_key: str,
    stance: str,
    round_idx: int,
) -> DebateState:
    """根据 LLM 输出的 payload 更新辩论状态。

    Args:
        state: 当前辩论状态
        payload: 从 DEBATE_STATE 解析的 dict
        speaker: 发言人显示名
        speaker_key: "bull" | "bear" | "neutral"
        stance: "bullish" | "bearish" | "neutral"
        round_idx: 当前轮次（1-based）
    """
    claims = dict(state.claims)

    # 更新已回应的 claims → addressed
    for cid in payload.get("responded_claim_ids", []):
        if cid in claims:
            claims[cid] = Claim(
                **{**claims[cid].to_dict(), "status": "addressed"}
            ) if not isinstance(claims[cid], dict) else claims[cid]
            if hasattr(claims[cid], 'status'):
                claims[cid].status = "addressed"

    # 更新已解决的 claims
    for cid in payload.get("resolved_claim_ids", []):
        if cid in claims and hasattr(claims[cid], 'status'):
            claims[cid].status = "resolved"

    # 更新未解决的 claims
    for cid in payload.get("unresolved_claim_ids", []):
        if cid in claims and hasattr(claims[cid], 'status'):
            claims[cid].status = "unresolved"

    # 创建新 claims
    new_claims_raw = payload.get("new_claims", [])
    prefix = speaker_key.upper()
    for nc in new_claims_raw:
        # 自动分配 ID
        existing = [c for c in claims if c.startswith(prefix)]
        claim_num = len(existing) + 1
        claim_id = f"{prefix}-{claim_num}"

        claim = Claim(
            claim_id=claim_id,
            speaker=speaker,
            speaker_key=speaker_key,
            stance=stance,
            claim=str(nc.get("claim", ""))[:200],
            evidence=[str(e) for e in nc.get("evidence", [])[:5]],
            confidence=float(nc.get("confidence", 0.5)),
            status="open",
            target_claim_ids=[str(t) for t in nc.get("target_claim_ids", [])],
            round_index=round_idx,
        )
        claims[claim_id] = claim

    # 更新焦点
    focus = payload.get("focus_claim_ids", [])
    if not focus:
        # 默认聚焦未解决的 open claims
        focus = [
            cid for cid, c in claims.items()
            if c.status in ("open", "unresolved")
        ][:5]

    # 记录历史
    history_entry = {
        "speaker": speaker,
        "speaker_key": speaker_key,
        "stance": stance,
        "round_index": round_idx,
        "round_summary": payload.get("round_summary", ""),
        "new_claim_count": len(new_claims_raw),
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

    return DebateState(
        claims=claims,
        history=state.history + [history_entry],
        count=state.count + 1,
        focus_claim_ids=focus,
    )


# ─────────────────────────────────────────────────────────────────
# 辩论 Prompt 注入
# ─────────────────────────────────────────────────────────────────

def format_debate_context(state: DebateState) -> str:
    """生成辩论上下文，注入到 rebuttal 和 synthesis Agent 的 prompt 中。"""
    if not state.claims:
        return "（辩论尚未开始，请基于上游研究报告建立你的论点。）"

    lines = ["## 当前辩论状态\n"]

    # 按状态分组
    open_claims = [c for c in state.claims.values() if c.status == "open"]
    addressed = [c for c in state.claims.values() if c.status == "addressed"]
    resolved = [c for c in state.claims.values() if c.status == "resolved"]
    unresolved = [c for c in state.claims.values() if c.status == "unresolved"]

    if open_claims:
        lines.append("### 待回应的论点（Open）")
        for c in open_claims:
            lines.append(f"- **{c.claim_id}** [{c.speaker}]: {c.claim}")
            lines.append(f"  置信度: {c.confidence:.0%} | 证据: {'; '.join(c.evidence[:2])}")

    if addressed:
        lines.append("\n### 已被回应但未解决的论点（Addressed）")
        for c in addressed:
            lines.append(f"- **{c.claim_id}** [{c.speaker}]: {c.claim}")

    if resolved:
        lines.append("\n### 已解决的论点（Resolved）")
        for c in resolved:
            lines.append(f"- ~~{c.claim_id}: {c.claim}~~ ✅")

    if unresolved:
        lines.append("\n### 未解决的论点（Unresolved）")
        for c in unresolved:
            lines.append(f"- **{c.claim_id}** [{c.speaker}]: {c.claim} ⚠️")

    if state.focus_claim_ids:
        lines.append(f"\n### 本轮建议聚焦: {', '.join(state.focus_claim_ids)}")

    lines.append(f"\n当前轮次: {state.count} | 总 Claims: {len(state.claims)}")

    return "\n".join(lines)


def build_debate_instruction(speaker_key: str, state: DebateState) -> str:
    """生成辩论指令，注入到辩论 Agent 的 system_prompt 中。"""
    goal = get_round_goal(state.count)

    instruction = f"""
## 结构化辩论规则（硬性要求）

你正在参与一场 Claim 驱动的结构化辩论。当前目标：{goal}

### 输出格式要求
你**必须**在报告末尾附加以下结构化标记（JSON 放在 HTML 注释中）：

```
<!-- DEBATE_STATE: {{
  "responded_claim_ids": ["对方claim_id列表"],
  "new_claims": [
    {{
      "claim": "你的核心论点（30字以内）",
      "evidence": ["证据1", "证据2"],
      "confidence": 0.7,
      "target_claim_ids": ["你反驳的对方claim_id"]
    }}
  ],
  "resolved_claim_ids": ["你认为已解决的claim_id"],
  "unresolved_claim_ids": ["你认为仍未解决的claim_id"],
  "round_summary": "本轮辩论总结（一句话）"
}} -->
```

### Claim 纪律
1. 每个 new_claim 必须有具体证据支撑，不能空口立论
2. 反驳时必须引用对方的 claim_id，逐条回击
3. confidence 必须如实反映证据强度（0.0-1.0）
4. 诚实承认对方有理的点——强行否认会降低可信度
"""

    # 如果已有辩论上下文，附加当前状态
    if state.claims:
        instruction += "\n\n" + format_debate_context(state)

    return instruction
