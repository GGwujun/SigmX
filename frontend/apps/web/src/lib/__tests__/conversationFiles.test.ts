import { afterEach, describe, expect, it, vi } from "vitest";
import { buildConversationFiles, buildConversationMarkdown, downloadTextFile } from "../conversationFiles";
import type { ResearchConversationTurn, ResearchResult, ResearchTask } from "../researchApi";

const task = (overrides: Partial<ResearchTask> = {}): ResearchTask => ({
  id: "task-1", user_id: "user-1", question: "低估值 高股息", template_id: null,
  scope: { market: "A股" }, constraints: [], status: "succeeded", steps: [], error: null,
  created_at: "2026-10-24T10:00:00Z", started_at: "2026-10-24T10:00:00Z", finished_at: "2026-10-24T10:01:00Z",
  ...overrides,
});
const result = (overrides: Partial<ResearchResult> = {}): ResearchResult => ({
  task_id: "task-1", question: "低估值 高股息", template_id: null, summary: "筛选出 1 个候选。",
  source: "local_market_store", as_of: "2026-10-23", scope: { market: "A股" }, candidates: [],
  risks: ["数据存在延迟"], created_at: "2026-10-24T10:01:00Z",
  conclusions: [{ text: "银行板块估值处于低位", evidence_ids: [], stage: "valuation" }],
  agent_evidence: [{ id: "e1", field: "pe_ttm", value: 6, source: "local_market_store", as_of: "2026-10-23" }],
  ...overrides,
});
const turn = (t: ResearchTask, r: ResearchResult | null): ResearchConversationTurn => ({ task: t, events: [], result: r });

describe("buildConversationFiles", () => {
  it("每个已完成的 turn 派生 md 报告，有证据时再派生 json", () => {
    const files = buildConversationFiles([turn(task(), result())]);
    expect(files.map(file => file.name)).toEqual(["分析报告-01-低估值高股息.md", "证据数据-01.json"]);
    expect(files[0].kind).toBe("md");
    expect(files[0].typeLabel).toBe("文档");
    expect(files[1].kind).toBe("json");
    expect(files[1].typeLabel).toBe("数据");
  });

  it("文件名剔除操作系统不安全字符并截断到 8 字", () => {
    const files = buildConversationFiles([turn(task({ id: "task-2", question: "低估值/高股息:筛选? 测试*" }), result({ task_id: "task-2" }))]);
    expect(files[0].name).toBe("分析报告-01-低估值高股息筛选.md");
  });

  it("没有结论的 turn 不产出文件，无证据时不产出 json", () => {
    expect(buildConversationFiles([turn(task(), null)])).toEqual([]);
    const files = buildConversationFiles([turn(task(), result({ agent_evidence: [] }))]);
    expect(files.map(file => file.kind)).toEqual(["md"]);
  });

  it("md 内容包含摘要/阶段结论/风险/候选表与免责脚注", () => {
    const files = buildConversationFiles([turn(task(), result({
      candidates: [{ code: "000001.SZ", name: "平安银行", industry: "银行", close: 11.2, pe_ttm: 6, pb: 0.6, dividend_yield: 5, total_market_value: 2173, reason: "PE 6|股息率 5%", evidence: [] }],
    }))]);
    const md = files[0].build();
    expect(md).toContain("# 低估值 高股息");
    expect(md).toContain("## 摘要");
    expect(md).toContain("筛选出 1 个候选。");
    expect(md).toContain("## 分析结论");
    expect(md).toContain("1. **估值水平**　银行板块估值处于低位");
    expect(md).toContain("## 风险提示");
    expect(md).toContain("- 数据存在延迟");
    expect(md).toContain("## 候选标的");
    expect(md).toContain("| 平安银行 | 000001.SZ | 6 | 5% | PE 6/股息率 5% |");
    expect(md).toContain("不构成投资建议");
  });

  it("json 内容是结构化证据数据", () => {
    const files = buildConversationFiles([turn(task(), result())]);
    const data = JSON.parse(files[1].build());
    expect(data).toMatchObject({ task_id: "task-1", question: "低估值 高股息", as_of: "2026-10-23" });
    expect(data.evidence).toEqual([{ id: "e1", field: "pe_ttm", value: 6, source: "local_market_store", as_of: "2026-10-23" }]);
  });
});

describe("buildConversationMarkdown", () => {
  it("多轮对话合成为一份文档，失败轮写明未生成结论", () => {
    const md = buildConversationMarkdown([
      turn(task(), result()),
      turn(task({ id: "task-2", question: "再看看消费板块", status: "failed", error: "数据不可用" }), null),
    ]);
    expect(md).toContain("# SigmX 对话导出");
    expect(md).toContain("## 第 1 轮 · 低估值 高股息");
    expect(md).toContain("**估值水平**　银行板块估值处于低位");
    expect(md).toContain("## 第 2 轮 · 再看看消费板块");
    expect(md).toContain("（本轮执行失败）");
    expect(md).toContain("不构成投资建议");
  });
});

describe("downloadTextFile", () => {
  const createElement = document.createElement.bind(document);

  afterEach(() => {
    vi.restoreAllMocks();
    delete (URL as { createObjectURL?: unknown }).createObjectURL;
    delete (URL as { revokeObjectURL?: unknown }).revokeObjectURL;
    vi.useRealTimers();
  });

  it("通过 Blob 与隐藏 a 标签触发下载并回收对象 URL", () => {
    vi.useFakeTimers();
    const createObjectURL = vi.fn((_blob: Blob) => "blob:mock-url");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const anchors: HTMLAnchorElement[] = [];
    vi.spyOn(document, "createElement").mockImplementation(tagName => {
      const element = createElement(tagName);
      if (tagName.toLowerCase() === "a") anchors.push(element as HTMLAnchorElement);
      return element;
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    downloadTextFile("分析报告-01.md", "# 报告", "text/markdown;charset=utf-8");

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(anchors[0].download).toBe("分析报告-01.md");
    expect(anchors[0].href).toBe("blob:mock-url");
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector("a")).toBeNull();

    vi.advanceTimersByTime(1000);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});
