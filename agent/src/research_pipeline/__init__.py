"""六阶段研究编排器（Core 零行业词，垂类知识在 plugins/）。"""

from .arithmetic import (  # noqa: F401
    NumberAudit,
    audit_numbers,
    check_stated_arithmetic,
    claim_tokens,
    number_bound,
)
from .calc import calculation_id, run_calc, verify_calc, verify_calcs  # noqa: F401
from .fetchers import FETCHERS, fetch_dataset, write_fetch  # noqa: F401
from .fsutil import atomic_write_text, read_json_if_exists, sha256_text, write_json  # noqa: F401
from .ledger import Ledger, LedgerEntry  # noqa: F401
from .methodology import methodology_block, methodology_missing  # noqa: F401
from .orchestrator import (  # noqa: F401
    PipelineConfig,
    PipelineResult,
    StageResult,
    run_pipeline,
    verify_protected,
)
from .plugin import (  # noqa: F401
    ResearchPlugin,
    StageDatasets,
    StageSchema,
    StageValidationContext,
    merged_stage_schema,
    register_plugin,
    validate_plugin,
)
from .plugins import A_STOCK_DEEP_RESEARCH, a_stock_plugin  # noqa: F401
from .run_tools import (  # noqa: F401
    RunToolsError,
    TurnContext,
    call_run_tool,
    run_tools_as_specs,
    tool_result_text,
)
from .runner_adapter import (  # noqa: F401
    PipelineDispatchRunner,
    PipelineResearchRunner,
    default_runs_root,
    resolve_code,
)
from .stage_loop import TurnOutcome, run_stage_turn  # noqa: F401
from .stop_guard import StopGuard, stage_problems, valid_calcs  # noqa: F401
from .validator import (  # noqa: F401
    RunView,
    load_run_view,
    validate_against_schema,
    validate_stage,
    validate_stage_output_shape,
)
