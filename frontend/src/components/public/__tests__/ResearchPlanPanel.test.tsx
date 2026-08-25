import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResearchPlanPanel } from "../ResearchPlanPanel";
import type { ResearchPlan } from "@/lib/researchApi";

const plan: ResearchPlan = {
  id: "plan-1", question: "现金流改善且低估值", template_id: null, scope: { market: "A股", exclude_st: true },
  conditions: [
    { id: "c1", metric: "pe_ttm", label: "市盈率不高于 20 倍", operator: "<=", value: 20, period: null, benchmark: null, status: "supported", reason: null, alternatives: [] },
    { id: "c2", metric: "operating_cashflow_trend", label: "经营现金流持续改善", operator: null, value: null, period: "多期财报", benchmark: null, status: "unavailable", reason: "多期数据尚未接入", alternatives: [{ label: "改用低估值筛选", question: "寻找低估值公司" }] },
  ],
  ranking: [], datasets: [{ key: "valuation", name: "估值快照", status: "supported", as_of: null, coverage: null }],
  steps: [], constraints: [{ field: "pe_ttm", op: "<=", value: 20 }], executable: false,
  suggested_question: "寻找低估值公司",
};

describe("ResearchPlanPanel", () => {
  it("blocks unavailable plans and offers an executable version", () => {
    const onUseSuggested = vi.fn();
    render(<ResearchPlanPanel plan={plan} onUseSuggested={onUseSuggested} onRun={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText("可执行")).toBeInTheDocument();
    expect(screen.getByText("暂不可用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始研究" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "采用可执行版本" }));
    expect(onUseSuggested).toHaveBeenCalledWith("寻找低估值公司");
  });
});
