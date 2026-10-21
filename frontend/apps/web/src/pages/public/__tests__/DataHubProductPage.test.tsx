import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DataHubProductPage } from "../DataHubProductPage";

describe("DataHubProductPage", () => {
  it("positions Data Hub as the data infrastructure behind agents and skills", () => {
    render(<MemoryRouter><DataHubProductPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /让 AI 智能体直接使用/ })).toBeInTheDocument();
    expect(screen.getByText(/Web 投研、投研 Skills 和本地智能体背后的数据基础设施/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /进入控制台/ })).toHaveAttribute("href", "/account/data-hub");
  });

  it("links product education to docs, skills, and credential activation", () => {
    render(<MemoryRouter><DataHubProductPage /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /查看 API 文档/ })).toHaveAttribute("href", "/docs/data-hub/");
    expect(screen.getByRole("link", { name: "浏览投研 Skills" })).toHaveAttribute("href", "/skills");
    expect(screen.getByRole("link", { name: "开通 Data Hub" })).toHaveAttribute("href", "/account/data-hub");
  });
});
