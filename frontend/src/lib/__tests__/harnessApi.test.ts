import { cancelHarnessRun, createHarnessRun, getHarnessRun, getHarnessRuns, getHarnessStatus } from "../harnessApi";

describe("harnessApi", () => {
  it("loads the authenticated Harness status contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ runtime_available: true, governance_ceiling: "simulate" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getHarnessStatus();

    expect(fetchMock).toHaveBeenCalledWith("/api/harness/status", expect.objectContaining({
      headers: expect.any(Object),
    }));
  });

  it("supports the authoritative run lifecycle and filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) });
    vi.stubGlobal("fetch", fetchMock);

    await getHarnessRuns(20, { runType: "research", status: "running" });
    await createHarnessRun({ run_type: "research", title: "茅台研究", goal: "验证盈利质量", context_manifest: {} });
    await getHarnessRun("run 1");
    await cancelHarnessRun("run 1");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/harness/runs?limit=20&run_type=research&status=running");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "POST", body: expect.any(String) }));
    expect(fetchMock.mock.calls[2][0]).toBe("/api/harness/runs/run%201");
    expect(fetchMock.mock.calls[3][0]).toBe("/api/harness/runs/run%201/cancel");
  });
});
