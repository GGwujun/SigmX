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

export interface StageConversationBlock {
  kind: "stage";
  id: string;
  stage: string;
  status: "running" | "completed" | "error";
  partial?: boolean;
  gaps?: string[];
}

export interface FinalConversationBlock {
  kind: "final";
  id: string;
  summary: string;
  conclusions: Array<{ text: string; evidence_ids: string[]; stage?: string }>;
  risks: string[];
  result: ResearchResult | null;
}

export type ResearchConversationBlock =
  | AssistantConversationBlock
  | ToolConversationBlock
  | StageConversationBlock
  | FinalConversationBlock;

const TOOL_LABELS: Record<string, string> = {
  search_market_data: "查询研究数据",
  load_research_skill: "加载研究方法",
  screen_financial_quality: "筛选财务质量",
};

// 六阶段管线（a_stock_deep_research）的阶段与受控工具中文名。
// pipeline_* 事件里未识别的一律忽略（reducer 对未知事件天然跳过）。
export const STAGE_LABELS: Record<string, string> = {
  profile: "公司画像",
  valuation: "估值水平",
  funds_sentiment: "资金与情绪",
  risk: "风险与反证",
  report: "成文",
};

export const stageLabel = (stage: string) => STAGE_LABELS[stage] || stage;

const PIPELINE_TOOL_LABELS: Record<string, string> = {
  calculate: "计算核验",
  write_stage: "落盘阶段产物",
  write_report: "撰写报告",
  read_run_file: "读取运行文件",
  list_run_files: "清点运行文件",
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

    // ---- 六阶段管线事件（plan.pipeline == a_stock_deep_research）----

    if (event.type === "pipeline_stage_started") {
      const stage = stringValue(event.payload.stage);
      if (!stage) continue;
      const running = blocks.some(block => block.kind === "stage" && block.stage === stage && block.status === "running");
      if (!running) blocks.push({ kind: "stage", id: `stage-${stage}`, stage, status: "running" });
      continue;
    }

    if (event.type === "pipeline_stage_completed" || event.type === "pipeline_stage_failed") {
      const stage = stringValue(event.payload.stage);
      const block = [...blocks].reverse().find(
        (item): item is StageConversationBlock => item.kind === "stage" && item.stage === stage && item.status === "running",
      );
      if (!block) continue;
      if (event.type === "pipeline_stage_failed") {
        block.status = "error";
      } else {
        block.status = "completed";
        block.partial = event.payload.partial === true || undefined;
        if (Array.isArray(event.payload.gaps)) block.gaps = event.payload.gaps.map(String);
      }
      continue;
    }

    if (event.type === "pipeline_dataset_fetched") {
      const dataset = stringValue(event.payload.dataset);
      if (!dataset) continue;
      blocks.push({
        kind: "tool",
        id: `tool-${event.id}`,
        tool: `fetch:${dataset}`,
        label: `取数 · ${dataset}`,
        status: event.payload.status === "error" ? "error" : "completed",
        evidenceCount: numberValue(event.payload.rows),
      });
      continue;
    }

    if (event.type === "pipeline_tool_ok" || event.type === "pipeline_tool_error") {
      const tool = stringValue(event.payload.tool);
      blocks.push({
        kind: "tool",
        id: `tool-${event.id}`,
        tool: `pipeline:${tool}`,
        label: PIPELINE_TOOL_LABELS[tool] || tool || "执行工具",
        status: event.type === "pipeline_tool_ok" ? "completed" : "error",
      });
      continue;
    }

    if (event.type === "pipeline_gate_rewrite") {
      const attempt = numberValue(event.payload.attempt);
      blocks.push({
        kind: "tool",
        id: `tool-${event.id}`,
        tool: "pipeline:gate_rewrite",
        label: attempt ? `报告合规重写（第 ${attempt} 次）` : "报告合规重写",
        status: "completed",
      });
      continue;
    }

    if (event.type === "pipeline_gate_failed") {
      blocks.push({ kind: "tool", id: `tool-${event.id}`, tool: "pipeline:gate", label: "报告合规检查", status: "error" });
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
