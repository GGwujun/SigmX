import { render, screen } from "@testing-library/react";

import { HarnessOverview } from "../HarnessOverview";

describe("HarnessOverview", () => {
  it("shows runtime mode, governance, dual credits and partial state", () => {
    render(<HarnessOverview status={{
      runtime_available: true,
      cloud_connected: false,
      local_data_available: true,
      data_hub_available: true,
      research_credits: 42,
      data_credits: 900,
      governance_ceiling: "simulate",
      degradations: ["cloud device is not connected"],
    }} runs={[{
      run_id: "run-1", run_type: "session", status: "completed",
      started_at: "2026-08-15T00:00:00Z", finished_at: null,
      context_manifest: {}, tool_calls: ["market.snapshot"], evidence_refs: [],
      costs: { research_credit: 2 }, degradations: [], result_ref: null,
    }]} dataMode="standalone" />);

    expect(screen.getByText("Standalone · 本地优先")).toBeInTheDocument();
    expect(screen.getByText("最高治理级别：模拟")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
    expect(screen.getByText("cloud device is not connected")).toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });
});
