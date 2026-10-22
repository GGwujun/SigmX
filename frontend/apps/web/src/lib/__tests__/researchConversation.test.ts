import { describe, expect, it } from "vitest";

import { buildResearchConversation } from "../researchConversation";
import type { ResearchEvent, ResearchResult } from "../researchApi";

const event = (id: number, type: string, payload: Record<string, unknown>): ResearchEvent => ({ id, type, payload });

describe("buildResearchConversation", () => {
  it("keeps model replies and tool activity in chronological Agent order", () => {
    const blocks = buildResearchConversation([
      event(1, "assistant_delta", { segment_id: "s1", delta: "先查行情。" }),
      event(2, "tool_call", { tool: "search_market_data", arguments: { query: "300253.SZ" } }),
      event(3, "tool_result", { tool: "search_market_data", status: "ok", evidence_count: 8, elapsed_ms: 120 }),
      event(4, "assistant_delta", { segment_id: "s2", delta: "行情显示估值偏低。" }),
      event(5, "assistant_final", { summary: "形成结论", conclusions: [], risks: [] }),
    ], null);

    expect(blocks).toEqual([
      { kind: "assistant", id: "s1", text: "先查行情。" },
      expect.objectContaining({ kind: "tool", id: "tool-2", label: "查询研究数据", status: "completed", evidenceCount: 8 }),
      { kind: "assistant", id: "s2", text: "行情显示估值偏低。" },
      expect.objectContaining({ kind: "final", id: "final-5", summary: "形成结论" }),
    ]);
  });

  it("merges adjacent deltas from the same public segment", () => {
    const blocks = buildResearchConversation([
      event(1, "assistant_delta", { segment_id: "s1", delta: "正在" }),
      event(2, "assistant_delta", { segment_id: "s1", delta: "核验数据。" }),
      event(3, "assistant_segment_done", { segment_id: "s1" }),
    ], null);

    expect(blocks).toEqual([{ kind: "assistant", id: "s1", text: "正在核验数据。" }]);
  });

  it("keeps one activity row when a tool emits both call and started events", () => {
    const blocks = buildResearchConversation([
      event(1, "tool_call", { tool: "load_research_skill" }),
      event(2, "tool_started", { tool: "load_research_skill" }),
      event(3, "tool_result", { tool: "load_research_skill", status: "ok" }),
    ], null);

    expect(blocks).toEqual([
      expect.objectContaining({ kind: "tool", label: "加载研究方法", status: "completed" }),
    ]);
  });

  it("never exposes raw thinking or final JSON text deltas", () => {
    const blocks = buildResearchConversation([
      event(1, "thinking_delta", { delta: "internal English reasoning" }),
      event(2, "text_delta", { delta: "{\"summary\":\"raw JSON\"}" }),
      event(3, "assistant_delta", { segment_id: "safe", delta: "正在核验公开数据。" }),
    ], null);

    expect(blocks).toEqual([{ kind: "assistant", id: "safe", text: "正在核验公开数据。" }]);
  });

  it("uses the stored result as a legacy final block when no final event exists", () => {
    const result = {
      task_id: "t1", question: "问题", template_id: null, summary: "旧任务结论", source: "local",
      as_of: null, scope: {}, candidates: [], risks: ["历史风险"], created_at: "2026-08-29",
      conclusions: [{ text: "旧结论", evidence_ids: [] }],
    } satisfies ResearchResult;

    const blocks = buildResearchConversation([], result);

    expect(blocks).toEqual([expect.objectContaining({ kind: "final", id: "legacy-final", summary: "旧任务结论", result })]);
  });
});

describe("buildResearchConversation · 六阶段管线事件", () => {
  it("maps stages, fetches and controlled tools into visible blocks", () => {
    const blocks = buildResearchConversation([
      event(1, "pipeline_started", { task_id: "p1", code: "600519", plugin: "a_stock", stages: ["profile"] }),
      event(2, "pipeline_dataset_fetched", { dataset: "security_master", status: "ok", rows: 1, stage: "profile" }),
      event(3, "pipeline_stage_started", { stage: "profile" }),
      event(4, "pipeline_tool_ok", { stage: "profile", tool: "calculate" }),
      event(5, "pipeline_tool_error", { stage: "profile", tool: "write_stage", code: "stage_schema_invalid" }),
      event(6, "pipeline_stage_completed", { stage: "profile" }),
    ], null);

    expect(blocks).toEqual([
      expect.objectContaining({ kind: "tool", id: "tool-2", label: "取数 · security_master", status: "completed", evidenceCount: 1 }),
      expect.objectContaining({ kind: "stage", id: "stage-profile", stage: "profile", status: "completed" }),
      expect.objectContaining({ kind: "tool", id: "tool-4", label: "计算核验", status: "completed" }),
      expect.objectContaining({ kind: "tool", id: "tool-5", label: "落盘阶段产物", status: "error" }),
    ]);
  });

  it("marks a partial stage with its data gaps and a failed stage as error", () => {
    const partial = buildResearchConversation([
      event(1, "pipeline_stage_started", { stage: "funds_sentiment" }),
      event(2, "pipeline_stage_completed", { stage: "funds_sentiment", partial: true, gaps: ["themes: 无数据"] }),
    ], null);
    expect(partial).toEqual([
      expect.objectContaining({ kind: "stage", stage: "funds_sentiment", status: "completed", partial: true, gaps: ["themes: 无数据"] }),
    ]);

    const failed = buildResearchConversation([
      event(3, "pipeline_stage_started", { stage: "risk" }),
      event(4, "pipeline_stage_failed", { stage: "risk", error: "校验未通过" }),
    ], null);
    expect(failed).toEqual([expect.objectContaining({ kind: "stage", stage: "risk", status: "error" })]);
  });

  it("surfaces report gate rewrites and failures as tool rows", () => {
    const blocks = buildResearchConversation([
      event(1, "pipeline_stage_started", { stage: "report" }),
      event(2, "pipeline_stage_completed", { stage: "report" }),
      event(3, "pipeline_gate_rewrite", { attempt: 1, problems: ["建议类表述"] }),
      event(4, "pipeline_gate_failed", { error: "重写次数用尽" }),
    ], null);

    expect(blocks).toEqual([
      expect.objectContaining({ kind: "stage", stage: "report", status: "completed" }),
      expect.objectContaining({ kind: "tool", id: "tool-3", label: "报告合规重写（第 1 次）", status: "completed" }),
      expect.objectContaining({ kind: "tool", id: "tool-4", label: "报告合规检查", status: "error" }),
    ]);
  });

  it("ignores loop noise (attempts, turns, replies, stop guard, lifecycle)", () => {
    const blocks = buildResearchConversation([
      event(1, "pipeline_stage_attempt_started", { stage: "profile", attempt: 1 }),
      event(2, "pipeline_turn_start", { stage: "profile", max_tool_rounds: 24 }),
      event(3, "pipeline_model_reply", { stage: "profile", round: 1, tool_calls: 2, finish_reason: "tool_calls" }),
      event(4, "pipeline_stop_guard_block", { stage: "profile", idle_streak: 1, blocks: 1, problems: ["缺产物"] }),
      event(5, "pipeline_stage_attempt_finished", { stage: "profile", attempt: 1, ok: true, rounds: 3 }),
      event(6, "pipeline_request_failed", { stage: "profile", round: 4, error: "TimeoutError" }),
      event(7, "pipeline_completed", { stages: { profile: "completed" } }),
    ], null);

    expect(blocks).toEqual([]);
  });

  it("keeps stage badges on legacy-final conclusions from pipeline results", () => {
    const result = {
      task_id: "t2", question: "深度研究 600519", template_id: null, summary: "六阶段完成", source: "pipeline",
      as_of: null, scope: {}, candidates: [], risks: [], created_at: "2026-10-22",
      conclusions: [{ text: "画像结论", evidence_ids: ["ev-security_master-0"], stage: "profile" }],
    } satisfies ResearchResult;

    const blocks = buildResearchConversation([], result);

    expect(blocks[0]).toEqual(expect.objectContaining({ kind: "final", id: "legacy-final" }));
    expect((blocks[0] as { conclusions: Array<{ stage?: string }> }).conclusions[0].stage).toBe("profile");
  });
});
