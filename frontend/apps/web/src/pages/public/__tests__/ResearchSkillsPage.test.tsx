import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchSkillsPage } from "../ResearchSkillsPage";

describe("ResearchSkillsPage service catalog", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders only skills returned by the published manifest service", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ skills: [{ slug: "dividend-analysis", name: "股息质量分析", description: "分析分红持续性。", updated_at: "2026-08-24T10:00:00Z", official: true, ownership: "official", ownership_label: "SigmX 官方", execution: "executable", primary_source: "data_hub", primary_source_label: "SigmX Data Hub", datahub_endpoints: ["stocks.dividends"], fallback_sources: ["akshare"], markets: ["CN_A"], credential_required: true, capability_status: "full" }] }), { status: 200 })));
    render(<MemoryRouter><ResearchSkillsPage /></MemoryRouter>);
    expect((await screen.findAllByRole("link", { name: "股息质量分析 查看详情" }))[0]).toHaveAttribute("href", "/skills/dividend-analysis");
    expect(screen.getByRole("heading", { name: "投研 Skills" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("搜索 Skills")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "常用 Skills" })).toBeInTheDocument();
    expect(screen.getAllByText("SigmX 官方")).not.toHaveLength(0);
    expect(screen.getAllByText("SigmX Data Hub")).not.toHaveLength(0);
    expect(screen.getAllByText("可执行")).not.toHaveLength(0);
    expect(screen.queryByText(/8\.6K|累计使用|预计消耗/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索投研 Skills"), { target: { value: "不存在" } });
    expect(screen.getByText("没有匹配的已发布 Skill")).toBeInTheDocument();
  });

  it("does not repeat featured skills in the all-skills grid", async () => {
    const skill = (slug: string, name: string) => ({ slug, name, description: `${name}说明`, updated_at: "2026-08-24T10:00:00Z", official: true, ownership: "official", ownership_label: "SigmX 官方", execution: "executable", primary_source: "data_hub", primary_source_label: "SigmX Data Hub", datahub_endpoints: [], fallback_sources: [], markets: ["CN_A"], credential_required: false, capability_status: "full" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ skills: [skill("one", "能力一"), skill("two", "能力二"), skill("three", "能力三")] }), { status: 200 })));

    render(<MemoryRouter><ResearchSkillsPage /></MemoryRouter>);

    const grid = await screen.findByTestId("research-skills-grid");
    expect(grid).not.toHaveTextContent("能力一");
    expect(grid).not.toHaveTextContent("能力二");
    expect(grid).toHaveTextContent("能力三");
  });
});
