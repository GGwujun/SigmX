import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchSkillsPage } from "../ResearchSkillsPage";

describe("ResearchSkillsPage service catalog", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders only skills returned by the published manifest service", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ skills: [{ slug: "dividend-analysis", name: "股息质量分析", description: "分析分红持续性。", updated_at: "2026-08-24T10:00:00Z", official: true, ownership: "official", ownership_label: "SigmX 官方", execution: "executable", primary_source: "data_hub", primary_source_label: "SigmX Data Hub", datahub_endpoints: ["stocks.dividends"], fallback_sources: ["akshare"], markets: ["CN_A"], credential_required: true, capability_status: "full" }] }), { status: 200 })));
    render(<MemoryRouter><ResearchSkillsPage /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "股息质量分析 查看详情" })).toHaveAttribute("href", "/skills/dividend-analysis");
    expect(screen.getByText("SigmX 官方")).toBeInTheDocument();
    expect(screen.getByText("SigmX Data Hub")).toBeInTheDocument();
    expect(screen.getByText("可执行")).toBeInTheDocument();
    expect(screen.queryByText(/8\.6K|累计使用|预计消耗/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索投研 Skills"), { target: { value: "不存在" } });
    expect(screen.getByText("没有匹配的已发布 Skill")).toBeInTheDocument();
  });
});
