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
