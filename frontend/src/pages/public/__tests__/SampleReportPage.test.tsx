import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { SampleReportPage } from "../SampleReportPage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/reports/sample/:slug" element={<SampleReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SampleReportPage", () => {
  it("renders the known sample report by slug", () => {
    renderAt("/reports/sample/alphaforge-demo");
    expect(screen.getByText("AlphaForge 研报样例（脱敏）")).toBeInTheDocument();
    expect(screen.getByText("公司概况")).toBeInTheDocument();
    expect(screen.getByText("财务质量")).toBeInTheDocument();
    expect(screen.getByText("脱敏样例 · 非真实研报")).toBeInTheDocument();
  });

  it("shows a not-found message for an unknown slug", () => {
    renderAt("/reports/sample/does-not-exist");
    expect(screen.getByText("未找到该样例报告")).toBeInTheDocument();
    expect(screen.getByText(/slug: does-not-exist/)).toBeInTheDocument();
  });
});
