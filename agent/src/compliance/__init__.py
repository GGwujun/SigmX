"""产物级合规 gate：确定性后处理，对抗提示注入与规避写法。"""

from .gate import (  # noqa: F401
    GateHit,
    GateResult,
    canonical_for_gate,
    compliance_gate,
    markdown_visible,
    missing_sections,
    normalize_report_status,
    probe_report_line,
    referenced_ids,
    report_status_token,
    validate_gate_rules,
)
from .gate_rules import GATE_RULES, PATTERNS, REGEXPS, gate_stage_patterns  # noqa: F401
