import { afterEach, describe, expect, it, vi } from "vitest";
import { createResearchPlan, createResearchTask } from "../researchApi";

describe("researchApi authentication recovery", () => {
  afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

  it("clears stale login state when the research service returns 401", async () => {
    localStorage.setItem("sigmx_auth_token", "expired-token");
    localStorage.setItem("sigmx_user", JSON.stringify({ id: "u1", email: "user@example.com" }));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "未登录或登录已过期" }), { status: 401 })));

    await expect(createResearchTask({ question: "低估值", template_id: null, scope: {}, constraints: [] })).rejects.toThrow("登录已过期，请重新登录");

    expect(localStorage.getItem("sigmx_auth_token")).toBeNull();
    expect(localStorage.getItem("sigmx_user")).toBeNull();
  });

  it("creates a public research plan before authenticated task execution", async () => {
    localStorage.setItem("sigmx_auth_token", "jwt-token");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      id: "plan-1", question: "低估值", template_id: null, scope: { market: "A股" },
      conditions: [], ranking: [], datasets: [], steps: [], constraints: [], executable: false,
      suggested_question: null,
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await createResearchPlan({ question: "低估值", template_id: null, scope: { market: "A股" } });

    expect(fetchMock).toHaveBeenCalledWith("/api/research/plans", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }));
  });
});
