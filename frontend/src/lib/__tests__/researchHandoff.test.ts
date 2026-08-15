import { consumePendingResearchHandoff, takeConsumedResearchHandoff } from "../researchHandoff";
import { setDesktopCloudAccessToken } from "../desktopConnectedSession";

describe("researchHandoff", () => {
  it("takes an opaque ticket once and keeps only safe payload in memory", async () => {
    const token = "sxrh_0123456789abcdef0123456789abcdef0123456789abcdef";
    vi.stubGlobal("sigmxDesktop", { isDesktop: true, researchHandoffTake: vi.fn().mockResolvedValue(token) });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "h1", kind: "saved_query", payload: { query: "低估值高股息" }, created_at: "now" }) }));
    setDesktopCloudAccessToken("cloud-access");

    expect(await consumePendingResearchHandoff()).toBe(true);
    expect(takeConsumedResearchHandoff()).toEqual({ kind: "saved_query", payload: { query: "低估值高股息" } });
    expect(takeConsumedResearchHandoff()).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });
});
