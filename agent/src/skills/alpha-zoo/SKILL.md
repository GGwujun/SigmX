---
name: alpha-zoo
description: Browse and bench the bundled alpha zoos — prebuilt cross-sectional factor libraries (Kakushadze 101, GTJA 191, Qlib 158, Fama-French / Carhart). Use when the user asks "which alphas exist", wants metadata on a named alpha, or wants to run IC/IR on a whole zoo over a universe.
category: research
sigmx:
  schema_version: 1
  ownership: official
  execution: instructional
  primary_source: data_hub
  datahub_endpoints:
    - stocks.daily
    - stocks.daily_basic
  fallback_sources:
    - akshare
  markets:
    - CN_A
  credentials:
    - SIGMX_DATA_HUB_BASE_URL
    - SIGMX_DATA_HUB_KEY
  capability_status: full
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

默认且优先使用 SigmX Data Hub；只在清单声明允许且指标口径一致时使用候补源。 `python -m src.skill_runtime.cli stocks.daily --params '<JSON>'`

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# Alpha Zoo

## Purpose

When the user asks about prebuilt cross-sectional alphas — Kakushadze 101, GTJA 191, Qlib 158, Fama-French / Carhart — or wants to bench a whole zoo on an investable universe (CSI 300, S&P 500, BTC-USDT, ...), this skill orients you. The zoo is the curated library; the bench is the evaluator.

## Tools Available

| Tool | When to use |
|------|------|
| `alpha_zoo` | Browse the library. `action=list_alphas` to enumerate (filterable by zoo / theme / universe), `action=get_alpha` for one alpha's metadata, `action=health` for registry load status. |
| `alpha_bench` | Run IC / IR on one alpha or a whole zoo over a universe + period. Emits an HTML report. |
| `factor_analysis` | Ad-hoc factor evaluation from a user-supplied factor CSV + return CSV. Use this when the user has their own factor (not in the zoo). |

## Decision Tree

- "list all momentum alphas" → `alpha_zoo` with `action=list_alphas, theme=momentum`.
- "show me gtja191_alpha_001" → `alpha_zoo` with `action=get_alpha, alpha_id=gtja191_alpha_001`.
- "bench all of GTJA 191 on CSI 300 from 2020 to 2024" → `alpha_bench` with `zoo=gtja191, universe=csi300, period=2020-2024`.
- "is the registry healthy" → `alpha_zoo` with `action=health` — surfaces `loaded`, `failed`, and per-error reasons.
- User uploads `my_factor.csv` → `factor_analysis` (zoo tools are for prebuilt alphas only).

## Zoo Inventory

| Zoo | Description | Approx. count |
|------|------|------|
| `kakushadze101` | Formulaic alphas from Kakushadze's 2015 paper. Mix of momentum, reversal, volume, and microstructure. | ~101 |
| `gtja191` | Guotai Junan 191 alphas — A-share focused cross-sectional factors. | ~191 |
| `qlib158` | Microsoft Qlib's 158 alpha factors — features tuned for ML pipelines. | ~158 |
| `classical` | Fama-French 3/5-factor + Carhart momentum. | <10 |

Counts are nominal; check `alpha_zoo action=health` for the live count currently loaded.

## Constraints

- **No per-stock per-date factor values are surfaced to the agent.** IC results are aggregate stats (mean / std / IR / positive-ratio); the HTML report shows top-N by IR plus formulas, never the underlying panel.
- **Lookahead is banned in the operator set.** `delta(df, d)` requires `d >= 1`; the negative-shift `Ref(df, -n)` form does not exist. See `docs/alpha-zoo/spec.md` for the full operator catalogue.
- **Universe loaders may not be wired for every market yet.** When `alpha_bench` returns `universe loader for X not yet implemented`, that's the W2 scaffold — the universe is recognised but the data pull lands in W4.
- **Do not expose absolute filesystem paths in agent output.** The bench tool writes to `~/.vibe-trading/reports/` by default; refer to it by that shorthand, not by the resolved absolute path.
- **`alpha_zoo` is read-only.** `alpha_bench` writes a single HTML file per run — no scratch state elsewhere.

## Common Pitfalls

- Filter mismatch on `list_alphas`: theme / universe must match the alpha's declared metadata exactly (e.g. `equity_cn`, not `cn` or `china`).
- Calling `alpha_bench` with both `alpha_id` and `zoo` set — they are mutually exclusive; pick one.
- Empty registry (`loaded=0`) means no zoo modules are populated yet; treat it as "zoos pending W3 porting" rather than a bug.

## Reference

- Operator catalogue: `docs/alpha-zoo/spec.md`
- Registry contract: `src/factors/registry.py` (frozen; do not modify)
- IC / layered NAV math: `src/factors/factor_analysis_core.py`
