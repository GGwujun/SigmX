import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResearchSkillsPage } from "../ResearchSkillsPage";

describe("ResearchSkillsPage service catalog", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("renders only skills returned by the published manifest service", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ skills: [{ slug: "dividend-analysis", name: "Dividend Analysis", description: "Analyze dividend sustainability.", updated_at: "2026-08-24T10:00:00Z", official: true }] }), { status: 200 })));
    render(<MemoryRouter><ResearchSkillsPage /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Dividend Analysis 查看详情" })).toHaveAttribute("href", "/skills/dividend-analysis");
    expect(screen.queryByText(/8\.6K|累计使用|预计消耗/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("搜索投研 Skills"), { target: { value: "不存在" } });
    expect(screen.getByText("没有匹配的已发布 Skill")).toBeInTheDocument();
  });
});
