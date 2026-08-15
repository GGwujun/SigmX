import { getHarnessStatus } from "../harnessApi";

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
});
