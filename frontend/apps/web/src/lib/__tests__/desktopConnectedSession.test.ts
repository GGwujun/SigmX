import { restoreDesktopConnectedSession } from "../desktopConnectedSession";

describe("restoreDesktopConnectedSession", () => {
  it("rotates the device token and installs an ephemeral Data Hub credential", async () => {
    const save = vi.fn().mockResolvedValue(true);
    vi.stubGlobal("sigmxDesktop", {
      isDesktop: true,
      cloudAccountLoad: vi.fn().mockResolvedValue({ refresh_token: "old", device_id: "d1" }),
      cloudAccountSave: save,
    });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: "ok", access_token: "access", refresh_token: "new" }) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ plaintext: "sxd_live_temp" }) }));

    expect(await restoreDesktopConnectedSession()).toBe(true);
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ refresh_token: "new", device_id: "d1" }));
    expect(sessionStorage.getItem("sigmx_desktop_data_hub_key")).toBe("sxd_live_temp");
  });
});
