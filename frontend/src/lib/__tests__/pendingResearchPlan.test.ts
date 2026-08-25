import { afterEach, describe, expect, it } from "vitest";
import { clearPendingResearchPlan, loadPendingResearchPlan, savePendingResearchPlan } from "../pendingResearchPlan";
import type { ResearchPlan } from "../researchApi";

const plan: ResearchPlan = {
  id: "plan-1",
  question: "寻找低估值公司",
  template_id: null,
  scope: { market: "A股" },
  conditions: [],
  ranking: [],
  datasets: [],
  steps: [],
  constraints: [],
  executable: false,
  suggested_question: null,
};

describe("pendingResearchPlan", () => {
  afterEach(() => sessionStorage.clear());

  it("round-trips a pending plan without persisting identity or credentials", () => {
    savePendingResearchPlan({ question: plan.question, templateId: null, plan });

    expect(loadPendingResearchPlan()).toEqual({ question: plan.question, templateId: null, plan });
    expect(sessionStorage.getItem("sigmx.pendingResearchPlan.v1")).not.toContain("token");
  });

  it("removes malformed pending state instead of restoring it", () => {
    sessionStorage.setItem("sigmx.pendingResearchPlan.v1", JSON.stringify({ question: "低估值" }));

    expect(loadPendingResearchPlan()).toBeNull();
    expect(sessionStorage.getItem("sigmx.pendingResearchPlan.v1")).toBeNull();
  });

  it("clears a restored plan explicitly", () => {
    savePendingResearchPlan({ question: plan.question, templateId: null, plan });
    clearPendingResearchPlan();
    expect(loadPendingResearchPlan()).toBeNull();
  });
});
