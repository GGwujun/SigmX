import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { HarnessRunsPage } from "../HarnessRunsPage";

vi.mock("@/lib/harnessApi", () => ({
  getHarnessRuns: vi.fn().mockResolvedValue([{
    run_id: "r1", run_type: "research", title: "贵州茅台盈利质量研究", goal: "验证现金流",
    status: "succeeded", created_at: "2026-08-16T03:00:00Z", started_at: "2026-08-16T03:00:00Z",
    finished_at: "2026-08-16T03:01:00Z", context_manifest: {}, steps: [], tool_calls: [],
    evidence: [{ id: "e1", kind: "dataset", title: "财务快照", ref: "data://finance", source: "Data Hub", data_version: "20260815" }],
    artifacts: [], costs: { data_credit: 3 }, degradations: [], governance_events: [], result_ref: "artifact://report", error: null,
  }]),
}));

describe("HarnessRunsPage", () => {
  it("renders the authoritative run ledger with evidence and costs", async () => {
    render(<MemoryRouter><HarnessRunsPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "运行中心" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("贵州茅台盈利质量研究")).toBeInTheDocument());
    expect(screen.getByText("财务快照")).toBeInTheDocument();
    expect(screen.getByText("3 Data Credit")).toBeInTheDocument();
  });
});
