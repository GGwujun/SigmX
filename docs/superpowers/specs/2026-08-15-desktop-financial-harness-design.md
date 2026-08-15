# SigmX Desktop Financial Harness 收口设计

**日期：** 2026-08-15  
**状态：** 总架构已批准，进入实施

## 1. 目标与边界

本项目不重写 Agent、Swarm、Session、Goal、MarketStore、回测或 Live Runtime，而是在其上建立统一的 Financial Harness 产品契约。Desktop 用户应能回答五个问题：本次研究用了什么数据、什么工具、什么上下文、处于什么治理等级、运行结果与成本如何复现。

Web 不加载 Harness API 或本地运行状态。真实交易执行仍是非目标；已有 Live Runtime 保持独立强约束，Harness 只读取其治理状态。

## 2. 统一契约

### 2.1 Tool Descriptor

每个对研究可见的工具映射为：

- `id`、`name`、`category`；
- `input_schema`、`output_kind`；
- `data_locality`: `local | data_hub | network | mixed`；
- `governance_level`: `read | propose | simulate | approve | execute`；
- `requires_confirmation`；
- `cost_dimensions`: `research_credit | data_credit | local_compute | none`。

默认工具最高只能声明 `simulate`。`approve` 表示人工批准动作，不代表自动执行；`execute` 不在当前 Registry 注册。

### 2.2 Context Manifest

一次研究上下文只记录引用与摘要，不复制私有内容：云自选、当前标的、风险偏好引用、历史研究引用、市场快照版本、本地文件引用及其 `local_only` 标志。任何本地文件默认 `local_only=true`。

### 2.3 Run Envelope

现有 Session、Swarm 和本地 Runner 映射为统一只读 Envelope：`run_id`、`run_type`、`status`、`started_at`、`finished_at`、`context_manifest`、`tool_calls`、`evidence_refs`、`costs`、`degradations`、`result_ref`。原始运行存储仍为权威位置，Harness 不复制完整报告。

## 3. Desktop API 与界面

新增 Desktop-only API：

- `GET /api/harness/status`：Standalone/Connected、数据源、云设备、积分、运行统计、治理上限；
- `GET /api/harness/tools`：统一工具目录；
- `GET /api/harness/runs`：跨 Session/Swarm 的最近运行 Envelope；
- `GET /api/harness/runs/{id}`：单次运行的来源、证据、成本与降级状态；
- `POST /api/harness/context/preview`：上传前只生成本地上下文清单，不上传文件正文。

Desktop 首页增加 Harness Overview；Run Detail 使用统一 Envelope 展示来源、治理、成本和降级。API 仅允许本地 Desktop 或有效设备身份，公开 Web 不注册对应导航。

## 4. Connected 数据访问

设备授权成功后，Desktop 使用短期用户访问令牌调用 `POST /api/datahub/desktop-session`。服务端生成作用域受套餐限制、最长 24 小时的临时 `sxd_live_` Credential；明文只返回一次并仅保存在 Electron 安全会话中。启动新会话时旧临时 Credential 自动吊销或过期清理，不占用个人长期 Key 的 10 个上限。

Settings 中保留显式“开发者 Credential”输入作为调试模式，但 Connected 主流程不要求复制长期 Key。额度耗尽或云端不可达时显示明确降级，可切换 Standalone 自有数据源。

## 5. 错误与安全

- 适配某类 Run 失败不影响其他 Run；Envelope 标记 `partial` 和降级原因；
- Harness API 不返回密钥、文件正文、持仓或券商授权；
- `execute` 等级未注册时，任何工具都不能通过 UI 自行升级；
- 临时 Data Hub Credential 与个人账户、设备和到期时间绑定；
- 云端不可用时 Harness Status 仍返回本地运行与 Standalone 能力。

## 6. 验收

1. Tool Registry 能覆盖当前主要研究工具并证明无 `execute` 工具；
2. Session/Swarm/Runner 至少两类运行映射为统一 Envelope；
3. Desktop 首页显示模式、数据源、治理上限、最近运行与双积分；
4. Context Preview 证明本地文件正文不会进入响应或云端；
5. 设备授权后可自动获得短期 Data Hub Credential，过期凭证不占长期 Key 上限；
6. Web 模式无法访问 Desktop-only Harness 页面；
7. 单元、API、前端和构建测试通过。
