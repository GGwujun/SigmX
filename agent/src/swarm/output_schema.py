"""AlphaForge 报告结构化输出 Schema。

定义 report_writer Agent 输出必须遵循的 JSON 结构。
前端据此渲染结构化卡片（结论/技术面/基本面/作战计划），
替代或增强当前的纯 Markdown 显示。
"""

from __future__ import annotations

ALPHA_FORGE_DASHBOARD_SCHEMA: dict = {
    "type": "object",
    "required": ["symbol", "decision", "confidence", "dashboard"],
    "properties": {
        "symbol": {
            "type": "string",
            "description": "股票代码，如 300253.SZ"
        },
        "decision": {
            "type": "string",
            "enum": ["strong_buy", "buy", "hold", "sell", "strong_sell"],
            "description": "交易决策"
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "置信度 0-1"
        },
        "dashboard": {
            "type": "object",
            "required": ["core_conclusion", "battle_plan"],
            "properties": {
                "core_conclusion": {
                    "type": "object",
                    "properties": {
                        "one_sentence": {"type": "string", "description": "一句话核心结论（≤30字）"},
                        "signal_type": {"type": "string", "enum": ["🟢买入信号", "🟡持有观望", "🔴卖出信号", "⚠️风险警告"]},
                        "bull_bear_summary": {"type": "string", "description": "多空辩论总结（一句话）"},
                    }
                },
                "technical": {
                    "type": "object",
                    "properties": {
                        "trend": {"type": "string"},
                        "support": {"type": "number"},
                        "resistance": {"type": "number"},
                        "ma_alignment": {"type": "string"},
                        "trend_score": {"type": "number", "minimum": 0, "maximum": 100},
                    }
                },
                "fundamental": {
                    "type": "object",
                    "properties": {
                        "valuation": {"type": "string"},
                        "growth": {"type": "string"},
                        "quality_score": {"type": "number", "minimum": 0, "maximum": 100},
                    }
                },
                "capital_flow": {
                    "type": "object",
                    "properties": {
                        "main_net": {"type": "number"},
                        "northbound": {"type": "string"},
                        "sentiment": {"type": "string"},
                    }
                },
                "battle_plan": {
                    "type": "object",
                    "properties": {
                        "entry_price": {"type": "number"},
                        "stop_loss": {"type": "number"},
                        "target_1": {"type": "number"},
                        "target_2": {"type": "number"},
                        "risk_reward": {"type": "number"},
                    }
                },
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
                "catalysts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
            }
        }
    }
}


# ─────────────────────────────────────────────────────────────────
# 报告 writer 的 JSON 输出指令
# ─────────────────────────────────────────────────────────────────

REPORT_WRITER_JSON_INSTRUCTION = """
## 结构化输出（必须）

在 report.md 末尾（所有正文内容之后）附加以下 JSON 块，用于前端结构化渲染：

```json
<!-- ALPHA_FORGE_DASHBOARD: {
  "symbol": "股票代码",
  "decision": "strong_buy|buy|hold|sell|strong_sell",
  "confidence": 0.75,
  "dashboard": {
    "core_conclusion": {
      "one_sentence": "一句话结论",
      "signal_type": "🟢买入信号",
      "bull_bear_summary": "多空总结"
    },
    "technical": {
      "trend": "趋势描述",
      "support": 支撑价,
      "resistance": 阻力价,
      "ma_alignment": "均线状态",
      "trend_score": 70
    },
    "fundamental": {
      "valuation": "估值评价",
      "growth": "成长性",
      "quality_score": 65
    },
    "capital_flow": {
      "main_net": 主力净流入(万),
      "northbound": "北向方向",
      "sentiment": "资金情绪"
    },
    "battle_plan": {
      "entry_price": 入场价,
      "stop_loss": 止损价,
      "target_1": 目标1,
      "target_2": 目标2,
      "risk_reward": 盈亏比
    },
    "risk_factors": ["风险1", "风险2"],
    "catalysts": ["催化1", "催化2"]
  }
} -->
```

所有数值必须来自上游 Agent 的实际产出。价格保留两位小数。决策必须与 PM 的最终裁决一致。
"""
