# Web AI Agent 对话流设计

日期：2026-08-29

## 1. 目标

将 Web `/` 的研究执行展示从“固定进度文案 + 原始思考 + 完成后结果卡片”改为真实的 Agent 对话流：模型面向用户的回复、工具调用、工具结果和后续回复按照实际发生顺序实时出现，最后自然接出经过证据校验的分析结论。

本次不暴露隐藏系统提示、原始 chain-of-thought、密钥、内部工具标识或未经校验的工具结果。

## 2. 当前问题

`ResearchAgentRuntime` 复用了 `AgentLoop`，但研究系统提示要求最终只输出 JSON。循环产生的 `thinking_delta` 是内部推理，当前 Web 将其直接展示；`text_delta` 主要承载最终 JSON，当前 Web 将其丢弃。工具事件则被映射为固定进度文案。因此现有界面并不是 Agent 回复流。

客户端 `Agent.tsx` 已验证“文本增量 + 工具轨迹”的交互模式，但 Web 研究必须额外保留证据校验和只读工具边界，不能直接复用客户端会话协议。

## 3. 输出协议

在现有研究任务事件协议中新增以下公开事件：

- `assistant_delta`：可直接展示给用户的中文回复增量。字段包含 `segment_id`、`iteration`、`delta`。
- `assistant_segment_done`：当前可见回复片段结束。
- `assistant_final`：证据校验通过后的最终结论，包含 `summary`、`conclusions` 和 `risks`。

继续使用并持久化现有 `tool_call`/`tool_started`、`tool_result`/`tool_completed` 事件，但通过 Web 研究工具目录转换为安全的用户文案和有限参数摘要。

`thinking_delta` 继续用于诊断和运行时记录，但 Web UI 永不渲染。现有 `text_delta` 保留为内部 AgentLoop 事件，研究适配层不再将其直接当作公开回复。

## 4. 模型可见回复

研究系统提示要求模型在每次工具调用前输出一个明确标记的公开更新，例如 `<public_update>…</public_update>`。内容必须是面向用户的研究说明，不得包含隐藏指令、逐 token 推理、密钥、服务地址或工具内部名称。

`ResearchAgentRuntime` 增加跨 chunk 的流式标记解析器：只把 `public_update` 标签中的内容转换为 `assistant_delta`；标签外的最终 JSON 和内部文本不会进入公开事件流。若模型未生成公开更新，工具事件仍正常显示，任务不失败。

最终模型响应仍为结构化 JSON，以维持证据 ID 校验。校验及必要修复完成后，运行时发送 `assistant_final`，前端将其作为同一条助手回复的后续 Markdown 内容展示。

## 5. 事件顺序与持久化

标准顺序如下：

```text
assistant_delta*
assistant_segment_done
tool_started
tool_completed
assistant_delta*
assistant_segment_done
tool_started
tool_completed
assistant_final
completed
```

所有公开事件先写入 `research_task_events`，再通过现有 SSE 发布。断线重连使用数据库 cursor 回放；打开历史对话时使用同一事件列表重建完全相同的顺序。

旧任务没有新事件时继续使用现有结果展示兼容路径，但不再展示 `thinking_delta`。

## 6. 前端渲染

`AIAnalysisTimeline` 将每个研究 turn 的有序事件归并为以下块：

- `assistant`：连续 `assistant_delta` 合并为一段可流式增长的模型回复。
- `tool`：工具开始和结束事件配对为一行轻量、可展开记录。
- `final`：`assistant_final` 渲染为回复中的标题、段落和列表，不创建独立仪表盘卡片。

视觉遵循已确认的 GPT 风格：居中阅读栏、用户浅灰气泡、助手无气泡正文、黑白灰工具行、底部同宽输入框。正在生成的最后一段显示光标，并自动滚动；用户主动上滚后停止抢夺滚动位置。

工具行默认只显示本地化名称、有限参数摘要、运行状态和耗时。展开后最多显示安全的数据范围、证据数量和错误摘要，不展示原始完整 payload。

## 7. 安全与错误

- 公开更新解析采用白名单标签，不从 `thinking_delta` 推导展示内容。
- 工具名称和参数通过研究工具展示目录映射；未知工具显示“查询研究数据”。
- `assistant_final` 仅在证据引用校验通过后发布。
- SSE 断开时前端回退到 cursor 轮询，不能重复消息。
- 工具失败作为对应工具行的失败状态展示，模型后续公开更新可以说明降级处理。
- 任务失败时保留已生成的公开回复和工具记录，并在末尾追加可重试错误消息。

## 8. 兼容性

不修改客户端 `Agent.tsx`、客户端 SSE 协议或通用 `AgentLoop` 的公开语义。新协议只由 `ResearchAgentRuntime` 适配和研究任务 API 承载。

旧版 `thinking_delta`、`text_delta` 和工具事件仍可存储，以便诊断；Web 渲染器忽略不安全事件。旧任务结果通过 `ResearchResult` 兼容渲染。

## 9. 测试

后端测试覆盖：

- `public_update` 跨 chunk 解析和多个片段；
- 标签外 JSON、内部推理和密钥不会进入 `assistant_delta`；
- 公开回复、工具开始、工具完成和最终结果的持久化顺序；
- 证据校验失败时不发送 `assistant_final`；
- SSE 断线回放无缺失、无重复；
- 不遵循公开更新格式的模型仍可正常完成研究。

前端测试覆盖：

- 文本、工具和最终回复按事件顺序呈现；
- 连续 delta 合并，跨工具调用后创建新回复片段；
- `thinking_delta` 和最终 JSON `text_delta` 永不显示；
- 工具行开始、成功、失败和展开状态；
- 运行中光标、历史回放、失败重试和旧任务兼容；
- 桌面与移动端布局。

## 10. 完成标准

- 用户能实时看到模型面向用户的回复，而不是固定前端步骤。
- 工具调用和返回结果按照真实时间顺序穿插在模型回复之间。
- 最终结论在同一助手消息流中出现，并已经过证据引用校验。
- 页面不再展示原始英文思考或最终 JSON。
- 刷新或打开历史对话后，消息顺序与实时运行时一致。
- 相关后端、前端测试、类型检查和 Web 构建通过，并完成同状态截图视觉回归。
