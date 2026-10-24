/**
 * 「输出」面板的文件派生：从对话真实研究结果生成可预览/下载的 md 报告与 json 证据。
 * 管线 report.md 不经 HTTP 暴露，这里由前端从 ResearchResult（摘要/结论/风险/候选/证据）
 * 确定性重建——内容全部来自真实返回，不虚构字段。
 */
import type { ResearchConversationTurn, ResearchResult } from "@/lib/researchApi";
import { stageLabel } from "@/lib/researchConversation";

export interface ConversationFile {
  id: string;
  name: string;
  kind: "md" | "json";
  typeLabel: "文档" | "数据";
  /** 惰性生成内容：面板只展示名字，点开/下载时才拼文本。 */
  build: () => string;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Windows/浏览器都不安全的文件名字符全部剔除。 */
function safeNamePart(question: string, length = 8): string {
  return question.replace(/[\\/:*?"<>|\s]+/g, "").slice(0, length);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function reportMarkdown(turn: ResearchConversationTurn): string {
  const result = turn.result as ResearchResult;
  const lines: string[] = [
    `# ${turn.task.question}`,
    "",
    `> SigmX 研究报告 · 生成于 ${formatDateTime(turn.task.finished_at || turn.task.created_at)} · 数据截至 ${result.as_of ?? "—"}`,
    "",
    "## 摘要",
    "",
    result.summary,
  ];
  const conclusions = result.conclusions ?? [];
  if (conclusions.length) {
    lines.push("", "## 分析结论", "");
    conclusions.forEach((item, index) => {
      lines.push(`${index + 1}. ${item.stage ? `**${stageLabel(item.stage)}**　` : ""}${item.text}`);
    });
  }
  if (result.risks.length) {
    lines.push("", "## 风险提示", "");
    result.risks.forEach(risk => lines.push(`- ${risk}`));
  }
  if (result.candidates.length) {
    lines.push("", "## 候选标的", "", "| 名称 | 代码 | PE(TTM) | 股息率 | 入选理由 |", "| --- | --- | --- | --- | --- |");
    result.candidates.forEach(item => {
      lines.push(`| ${item.name} | ${item.code} | ${item.pe_ttm ?? "—"} | ${item.dividend_yield == null ? "—" : `${item.dividend_yield}%`} | ${item.reason.replace(/\|/g, "/")} |`);
    });
  }
  lines.push("", "---", "", "AI 分析仅供研究参考，不构成投资建议。", "");
  return lines.join("\n");
}

/** 菜单「导出对话 Markdown」：整段对话（含每轮问题与结论）合成一份文档。 */
export function buildConversationMarkdown(turns: ResearchConversationTurn[]): string {
  const parts: string[] = ["# SigmX 对话导出", "", `> 导出时间 ${formatDateTime(new Date().toISOString())} · 共 ${turns.length} 轮对话`, ""];
  turns.forEach((turn, index) => {
    parts.push(`## 第 ${index + 1} 轮 · ${turn.task.question}`, "");
    if (turn.result) {
      parts.push(turn.result.summary, "");
      (turn.result.conclusions ?? []).forEach((item, i) => {
        parts.push(`${i + 1}. ${item.stage ? `**${stageLabel(item.stage)}**　` : ""}${item.text}`);
      });
      if (turn.result.risks.length) parts.push("", "风险提示：", ...turn.result.risks.map(risk => `- ${risk}`));
    } else {
      parts.push(`（本轮${turn.task.status === "failed" ? "执行失败" : "未生成结论"}）`, "");
    }
    parts.push("");
  });
  parts.push("---", "", "AI 分析仅供研究参考，不构成投资建议。", "");
  return parts.join("\n");
}

/** 「输出」面板文件清单：每个已有结论的 turn 派生一份 md 报告（+ 有证据时一份 json）。 */
export function buildConversationFiles(turns: ResearchConversationTurn[]): ConversationFile[] {
  const files: ConversationFile[] = [];
  turns.forEach((turn, index) => {
    if (!turn.result) return;
    const serial = pad(index + 1);
    const short = safeNamePart(turn.task.question);
    files.push({
      id: `${turn.task.id}-report`,
      name: `分析报告-${serial}${short ? `-${short}` : ""}.md`,
      kind: "md",
      typeLabel: "文档",
      build: () => reportMarkdown(turn),
    });
    if (turn.result.agent_evidence?.length) {
      files.push({
        id: `${turn.task.id}-evidence`,
        name: `证据数据-${serial}.json`,
        kind: "json",
        typeLabel: "数据",
        build: () => JSON.stringify({
          task_id: turn.task.id,
          question: turn.task.question,
          as_of: turn.result?.as_of ?? null,
          evidence: turn.result?.agent_evidence ?? [],
        }, null, 2),
      });
    }
  });
  return files;
}

/** 触发浏览器下载一段文本（Blob + 隐藏 a 标签，1s 后回收对象 URL）。 */
export function downloadTextFile(name: string, content: string, mime = "text/plain;charset=utf-8"): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
