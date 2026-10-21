import type { ResearchEvent, ResearchResult } from "./researchApi";

export interface AssistantConversationBlock {
  kind: "assistant";
  id: string;
  text: string;
}

export interface ToolConversationBlock {
  kind: "tool";
  id: string;
  tool: string;
  label: string;
  status: "running" | "completed" | "error";
  evidenceCount?: number;
  elapsedMs?: number;
}

export interface FinalConversationBlock {
  kind: "final";
  id: string;
  summary: string;
  conclusions: Array<{ text: string; evidence_ids: string[] }>;
  risks: string[];
  result: ResearchResult | null;
}

export type ResearchConversationBlock =
  | AssistantConversationBlock
  | ToolConversationBlock
  | FinalConversationBlock;

const TOOL_LABELS: Record<string, string> = {
  search_market_data: "查询研究数据",
  load_research_skill: "加载研究方法",
  screen_financial_quality: "筛选财务质量",
};

const stringValue = (value: unknown) => typeof value === "string" ? value : "";
const numberValue = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : undefined;

export function buildResearchConversation(
  events: ResearchEvent[],
  result: ResearchResult | null,
): ResearchConversationBlock[] {
  const blocks: ResearchConversationBlock[] = [];
  let hasFinalEvent = false;

  for (const event of events) {
    if (event.type === "assistant_delta") {
      const id = stringValue(event.payload.segment_id) || `assistant-${event.id}`;
      const delta = stringValue(event.payload.delta);
      if (!delta) continue;
      const previous = blocks[blocks.length - 1];
      if (previous?.kind === "assistant" && previous.id === id) previous.text += delta;
      else blocks.push({ kind: "assistant", id, text: delta });
      continue;
    }

    if (event.type === "tool_call" || event.type === "tool_started") {
      const tool = stringValue(event.payload.tool);
      if (event.type === "tool_started") {
        const pending = [...blocks].reverse().find(
          (item): item is ToolConversationBlock => item.kind === "tool" && item.tool === tool && item.status === "running",
        );
        if (pending) continue;
      }
      blocks.push({
        kind: "tool",
        id: `tool-${event.id}`,
        tool,
        label: TOOL_LABELS[tool] || "查询研究数据",
        status: "running",
      });
      continue;
    }

    if (event.type === "tool_result" || event.type === "tool_completed") {
      const tool = stringValue(event.payload.tool);
      const block = [...blocks].reverse().find(
        (item): item is ToolConversationBlock => item.kind === "tool" && item.tool === tool && item.status === "running",
      );
      if (!block) continue;
      block.status = event.payload.status === "error" ? "error" : "completed";
      block.evidenceCount = numberValue(event.payload.evidence_count);
      block.elapsedMs = numberValue(event.payload.elapsed_ms);
      continue;
    }

    if (event.type === "assistant_final") {
      hasFinalEvent = true;
      blocks.push({
        kind: "final",
        id: `final-${event.id}`,
        summary: stringValue(event.payload.summary) || result?.summary || "研究已完成",
        conclusions: Array.isArray(event.payload.conclusions)
          ? event.payload.conclusions as Array<{ text: string; evidence_ids: string[] }>
          : result?.conclusions ?? [],
        risks: Array.isArray(event.payload.risks) ? event.payload.risks.map(String) : result?.risks ?? [],
        result,
      });
    }
  }

  if (!hasFinalEvent && result) {
    blocks.push({
      kind: "final",
      id: "legacy-final",
      summary: result.summary,
      conclusions: result.conclusions ?? [],
      risks: result.risks,
      result,
    });
  }
  return blocks;
}
