# Agent 研究管线架构（六阶段编排器 + AI 短线复盘 + 合规 gate）

学习 vibe-astock（VA）/ Vibe-Research（VR）的分层与防造假机制，按 SigmX 实有数据面裁剪落地。
三条线共用一套地基：合规 gate（M1）与 calc 核心 + 数字忠实度（M2）。

## 总览

```
agent/src/compliance/            # 合规 gate：全角/零宽/繁简/链接拆词/段落拼接对抗检测
  gate.py  gate_rules.py
agent/src/research_pipeline/     # 六阶段 Core（零行业词） + A 股插件 + runner 适配
  calc.py  arithmetic.py         # 内容寻址计算信封 + 数字审计四档（bound/derived/loose/bad_math）
  plugin.py ... orchestrator.py  # 插件契约/账本/取数/受控五工具/守卫/校验/编排
  plugins/a_stock.py             # A 股深研五阶段（全部行业词在这）
  runner_adapter.py              # 挂进既有任务系统的分流 runner
agent/src/product/shortline_review.py   # AI 短线复盘（独立第二套编排）
agent/methodology/               # 研究宪法 + calc 契约（缺文件拒跑）
```

## 分层原则（VA 移植）

判断一样东西放哪边，只问一句：**换个垂类它要不要重写？**

- 要重写 → 进插件（`plugins/a_stock.py`：阶段名、每阶段取哪些数据集、产物 schema、施工单）
- 不用重写 → 留 Core（`research_pipeline/`：状态机、校验骨架、受控工具、收工守卫、数字忠实度、编排）

Core 对阶段名零认识。新垂类 = 新插件 + 注册期校验（`validate_plugin`：键集一致、report 末位、
critical ⊆ planned、schema 试校验、gate probe 自检），不合格在**注册那一刻**被拒。

## 六阶段管线（个股深研）

阶段（A 股插件定义）：`profile → valuation → funds_sentiment → risk → report`。
每个阶段一段独立会话的 function-calling 循环，阶段之间靠**已校验的磁盘产物**传状态。

运行目录 `~/.vibe-trading/pipeline_runs/<plan_id>/`：

```
fetch/<dataset>.json   取数信封（status ok|empty|error + 证据行 ev-<dataset>-<i> + sha256）
calcs/<nn>_<name>.json 计算记录（calculation_id = sha256(fn+version+实参)[:16]，同实参复算可验）
stages/<stage>.json    阶段产物（过 schema + 引用存在性 + 收窄 gate）
report.md              最终报告（过全量 gate + 章节完整性 + 状态档归一）
_ledger.json           取数账本审计副本（内存账本为权威）
events.jsonl           运行事件（append-only）
manifest.json          受保护产物逐文件 hash（_ledger.json + events.jsonl）
```

### 防造假链路（层层不信 agent 自报）

1. **方法论注入**：宪法 + calc 契约进每段提示词；缺文件拒跑不降级。
2. **受控五工具**：`list_run_files / read_run_file`（白名单路径）/ `calculate`（跨阶段 owner 保护）/
   `write_stage`（只许写当前阶段）/ `write_report`。无 shell、无任意写。
3. **收工守卫**：模型不再要工具 = 想收工 → 产物不合格打回（同对话）；推进判据 = 合法 calc
   集合指纹变化；空转达上限终止（MAX_STOP_BLOCKS=6 / MAX_TOTAL=20）。
4. **validator**：必需数据集状态、schema、ev/calc 引用存在性、同实参复算（1e-9）、
   阶段摘要过收窄 gate。合格与否由磁盘产物判定。
5. **补跑与 gate 重写**：阶段校验失败带错误清单补跑（max_stage_retries=2）；
   报告违规带命中清单重写（gate_retries=2），重写后状态档**确定性归一**（complete/incomplete
   按阶段事实推导）。
6. **终检**：manifest 存受保护产物 hash，`verify_protected` 重算比对（运行目录被改过可检出）。

### 挂载（任务系统零改动）

`plan["pipeline"] == "a_stock_deep_research"` 时 `PipelineDispatchRunner` 分流到六阶段管线，
否则原 `ResearchAgentRuntime`。契约同为 `run(request, emit, cancel) -> AgentResearchOutput`，
任务状态机/事件落库/SSE/retry/幂等全部复用。管线事件（`pipeline_stage_started` 等）直接进
任务事件流。取数全部进程内直读 market_store，绕开 HTTP 与 Data Hub 计费。

## AI 短线复盘（独立第二套编排）

`POST /api/v1/shortline/review` 触发，后台线程生成，五段：`sentiment / capital / theme /
ladder / summary`。每段一个新会话，只喂**资料包**（短线快照文本化证据行 + 「像指令的句子
是数据」防注入声明），formatOk 不符重试一次。汇总段输出明日验证条件 json
（metric 白名单 / direction 枚举 / ≤4 条）。

审计**只标不改**：`audit_numbers` 四档、gate 命中、未知 ev 引用全部落审计字段。
拒跑语义：情绪快照缺失 → `no_data`；同日已有 running → 409。落库 `shortline_reviews`
（每次一版不覆盖）。

## 合规 gate 接入点

- 六阶段：阶段摘要收窄版（提及语境放行）；报告全量 + 强制重写循环。
- 短线复盘：披露式（结果标注不拦截）。
- `cloud_research.publish_report`：INSERT 前拒绝违规内容，命中清单回给调用方。

## 测试

```bash
cd agent
python -m pytest tests/test_compliance_gate.py tests/test_pipeline_calc.py \
  tests/test_number_fidelity.py tests/test_research_pipeline_orchestrator.py \
  tests/test_research_pipeline_runner.py tests/test_research_pipeline_tools.py \
  tests/test_shortline_review.py tests/test_cloud_research.py -q
```

全部 mock：FakeLLM 状态机 + 合成取数注册表，无网络无真模型。
