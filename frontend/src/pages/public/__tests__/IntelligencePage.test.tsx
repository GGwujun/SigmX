import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntelligencePage } from "../IntelligencePage";

describe("IntelligencePage real feed", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("loads real articles, searches on the server, and opens the source detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify({
      articles: [{ title: "交易所发布回购新规", url: "https://example.com/news", source: "交易所", published: "2026-08-24", snippet: "新规完善回购披露要求。" }],
      query: new URL(String(input), "http://localhost").searchParams.get("q") ?? "", sources: ["交易所"], updated_at: "2026-08-24T10:00:00Z", cache_status: "fresh_cache", cached_until: "2026-08-24T10:10:00Z",
    }), { status: 200 })));
    render(<MemoryRouter><IntelligencePage /></MemoryRouter>);
    expect(await screen.findByText("交易所发布回购新规")).toBeInTheDocument();
    expect(screen.getByText("短期缓存命中 · 减少重复抓取")).toBeInTheDocument();
    expect(screen.queryByText(/演示/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /查看 交易所发布回购新规 新闻详情/ }));
    expect(within(screen.getByRole("dialog", { name: "情报详情" })).getByRole("link", { name: "查看原文" })).toHaveAttribute("href", "https://example.com/news");
    fireEvent.change(screen.getByLabelText("情报检索问题"), { target: { value: "回购" } });
    fireEvent.click(screen.getByRole("button", { name: "智能搜索" }));
    expect(await screen.findByText(/搜索“回购”/)).toBeInTheDocument();
    expect(fetch).toHaveBeenLastCalledWith("/api/public/intelligence?q=%E5%9B%9E%E8%B4%AD&limit=30");
  });
});
