import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchSkillDetailPage } from "../ResearchSkillDetailPage";

describe("ResearchSkillDetailPage service manifest", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders the real SKILL.md and installation modes without fake metrics", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ slug: "dividend-analysis", name: "Dividend Analysis", description: "Analyze dividend sustainability.", updated_at: "2026-08-24T10:00:00Z", official: true, content: "# Dividend Analysis\nUse stocks.daily_basic." }), { status: 200 })));
    render(<MemoryRouter initialEntries={["/skills/dividend-analysis"]}><Routes><Route path="/skills/:slug" element={<ResearchSkillDetailPage/>}/></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Dividend Analysis" })).toBeInTheDocument();
    expect(screen.getByText(/stocks.daily_basic/)).toBeInTheDocument();
    expect(screen.queryByText(/累计使用|预计消耗/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "CLI" }));
    expect(screen.getByTestId("install-command")).toHaveTextContent("sigmx skills install dividend-analysis");
  });
});
