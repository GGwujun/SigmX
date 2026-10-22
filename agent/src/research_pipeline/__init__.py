"""六阶段研究编排器（Core 零行业词，垂类知识在 plugins/）。"""

from .arithmetic import (  # noqa: F401
    NumberAudit,
    audit_numbers,
    check_stated_arithmetic,
    claim_tokens,
    number_bound,
)
from .calc import calculation_id, run_calc, verify_calc, verify_calcs  # noqa: F401
