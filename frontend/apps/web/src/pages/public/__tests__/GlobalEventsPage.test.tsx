import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlobalEventsPage } from "../GlobalEventsPage";

const item = { id: "event-1", title: "美联储释放谨慎降息信号", summary: "市场重新评估利率路径与风险资产表现。", event_type: "macro_policy", status: "active", importance: .86, confidence: .91, region: "美国", first_seen_at: "2026-08-29T01:15:00Z", updated_at: "2026-08-29T02:15:00Z", evidence_count: 8 };

describe("GlobalEventsPage", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders an editorial event timeline inside the existing shell", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [item] }), { status: 200 })));
    render(<MemoryRouter><GlobalEventsPage /></MemoryRouter>);
    expect(await screen.findByText(item.title)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "全球事件" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索事件、主题或地区")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "市场影响" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /让 AI 分析影响/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索全球事件"), { target: { value: "不存在" } });
    expect(screen.getByText("没有匹配的全球事件")).toBeInTheDocument();
  });
});
