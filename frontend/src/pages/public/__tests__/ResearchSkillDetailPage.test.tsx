import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchSkillDetailPage } from "../ResearchSkillDetailPage";

describe("ResearchSkillDetailPage service manifest", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders the real SKILL.md and installation modes without fake metrics", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ slug: "dividend-analysis", name: "股息质量分析", description: "分析分红持续性。", updated_at: "2026-08-24T10:00:00Z", official: true, ownership: "official", ownership_label: "SigmX 官方", execution: "executable", primary_source: "data_hub", primary_source_label: "SigmX Data Hub", datahub_endpoints: ["stocks.daily_basic", "stocks.dividends"], fallback_sources: ["akshare"], markets: ["CN_A"], credential_required: true, capability_status: "full", content: "# Dividend Analysis\nUse stocks.daily_basic." }), { status: 200 })));
    render(<MemoryRouter initialEntries={["/skills/dividend-analysis"]}><Routes><Route path="/skills/:slug" element={<ResearchSkillDetailPage/>}/></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "股息质量分析" })).toBeInTheDocument();
    expect(screen.getAllByText(/stocks.daily_basic/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("SigmX Data Hub").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("link", { name: "stocks.dividends" })).toHaveAttribute("href", expect.stringContaining("stocks.dividends"));
    expect(screen.getByText(/akshare/)).toBeInTheDocument();
    expect(screen.getByTestId("agent-install-prompt")).toHaveTextContent("SIGMX_DATA_HUB_KEY");
    expect(screen.queryByText(/累计使用|预计消耗/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "CLI" }));
    expect(screen.getByTestId("install-command")).toHaveTextContent("sigmx skills install dividend-analysis");
  });

  it("does not require a Data Hub credential for a public-source skill", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ slug: "akshare", name: "AKShare金融数据获取", description: "公共数据源。", updated_at: "2026-08-24T10:00:00Z", official: false, ownership: "third_party", ownership_label: "第三方", execution: "instructional", primary_source: "public_source", primary_source_label: "公共数据源", datahub_endpoints: [], fallback_sources: ["akshare"], markets: ["CN_A"], credential_required: false, capability_status: "full", content: "# AKShare" }), { status: 200 })));
    render(<MemoryRouter initialEntries={["/skills/akshare"]}><Routes><Route path="/skills/:slug" element={<ResearchSkillDetailPage/>}/></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "AKShare金融数据获取" })).toBeInTheDocument();
    expect(screen.getByTestId("agent-install-prompt")).not.toHaveTextContent("SIGMX_DATA_HUB_KEY");
    expect(screen.getByText("无需 Data Hub Credential")).toBeInTheDocument();
  });
});
