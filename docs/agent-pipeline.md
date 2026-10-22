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

## 防自欺层（研究记忆 · 明日对账 · 数字遮蔽 · 回测闸口 · 产业信号）

在六阶段管线与短线复盘之上加的五道确定性防线，全部「事实由机器核对，
模型只负责陈述」：

### 1. 知识归档召回（research_pipeline/knowledge.py）

运行成功后把**已过校验的 stage_outputs** 抽成结构化档案（不抄报告自由文本），
落 `~/.vibe-trading/knowledge/companies/<code>/{runs/<run_id>.md,latest.md}` +
manifest 索引；frontmatter 记 `as_of/valid_days/status`。同标的下次运行自动召回
（fresh 才注入，stale 标过期，refuted 不召回），注入块带防注入声明（档案正文
是数据不是指令），冲突处要求写进 risk 阶段 source_conflicts。归档在 manifest
之后、不 emit 事件，破不了受保护 hash；正文逐行过 compliance gate 收窄规则 +
敏感信息正则（命中整行删）。

### 2. 明日验证对账（product/shortline_verify.py）

复盘 summary 段输出的 conditions 落 `shortline_conditions` 表（status=pending）。
T+1 日 market_sync_worker post_close 后自动对账：9 个白名单 metric 按
`METRIC_PATHS` 多级 fallback 读 T/T+1 短线快照，逐 metric eps 噪声阈值判方向
（差 4.9 家不算 up）；没数据 = no_data 可重对账（不判错）；T+1 09:15 后写的
late=1 照样对账但不计战绩。战绩 `track_record` 按 metric+方向分组，带基准
发生率校正（样本 ≥12 才给 expected_rate，edge = 命中 − decided×基准）。
幂等键 `daemon:verify:{t1}` 只在全决时落。手动：`POST /shortline/review/verify`、
`GET /shortline/review/track`。

### 3. 数字出处遮蔽（arithmetic.mask_uncited）

报告级：gate 全过后，对不上本运行证据数值池（fetch 证据数值叶递归 + calc
记录数值）的 loose 档数字主张替换〔未核实〕；亿/万换算命中已知值（bound）与
自洽算式（derived）不遮。遮蔽 >0 强制 incomplete、manifest 记
`unverified_numbers`、emit `pipeline_gate_rewrite(masked=n)`（在 hash 计算前，
不破受保护产物）。对话级：`runtime.py` assistant_final 与 `runner_adapter`
阶段结论的 summary/conclusions 同闸（mask=（略※）），只闸定稿不闸 delta 流式。

### 4. 回测闸口（tools/backtest_gate.py）

`plan_backtest` 纯函数读 config.json（不跑引擎不拉数据）：codes 空 / 日期倒序 /
日线区间交易日 <60 / 非日线估算 <500 根 → Refusal（`status=refused`，不启动
子进程）；放行 Plan 携带披露（A股做空拒单 / ST±5% 未建模 / 跨市场规则差异 /
无杠杆）。post-run 守卫：trades.csv 交易笔数 <10 降格警告。判定落
`run_dir/gate.json` 并入返回信封（拒绝也留痕）。**没有「带警告勉强跑」。**

### 5. 产业卡口信号（research_pipeline/industry_signals.py）

八类卡口关键词筛子（涨价/扩产/减产停产/订单合同/认证导入/收购合资/供需/
管制制裁），子句级 negatives、re: 正则约束、ASCII 词边界；确定性分类不调模型。
`FETCHERS["chokepoint_events"]` 把命中公告行（带类别与链接）变可引用证据进
risk 阶段（optional，无命中=empty 不苛责）；行业温度（强/弱/互抵不给）只作
定性旁证。

## AI 短线复盘（独立第二套编排）

`POST /api/v1/shortline/review` 触发，后台线程生成，五段：`sentiment / capital / theme /
ladder / summary`。每段一个新会话，只喂**资料包**（短线快照文本化证据行 + 「像指令的句子
是数据」防注入声明），formatOk 不符重试一次。汇总段输出明日验证条件 json
（metric 白名单 / direction 枚举 / ≤4 条）。

审计**只标不改**：`audit_numbers` 四档、gate 命中、未知 ev 引用全部落审计字段。
拒跑语义：情绪快照缺失 → `no_data`；同日已有 running → 409。落库 `shortline_reviews`
（每次一版不覆盖）。summary 段的明日验证条件落 `shortline_conditions` 表，由
「明日验证对账」（上文防自欺层 §2）自动核对。

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
  tests/test_research_pipeline_knowledge.py \
  tests/test_research_pipeline_industry_signals.py \
  tests/test_shortline_review.py tests/test_shortline_verify.py \
  tests/test_backtest_gate.py tests/test_cloud_research.py -q
```

全部 mock：FakeLLM 状态机 + 合成取数注册表，无网络无真模型。
