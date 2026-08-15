import { setDataMode, setDesktopDataHubSessionKey } from "@/lib/dataMode";
import { createDesktopDataHubSession, refreshDeviceToken } from "@/lib/productApi";

let cloudAccessToken = "";

export function setDesktopCloudAccessToken(token: string): void { cloudAccessToken = token; }
export function getDesktopCloudAccessToken(): string { return cloudAccessToken; }

export async function restoreDesktopConnectedSession(): Promise<boolean> {
  const bridge = window.sigmxDesktop;
  if (!bridge?.isDesktop || !bridge.cloudAccountLoad) return false;
  const account = await bridge.cloudAccountLoad();
  if (!account?.refresh_token || !account.device_id) return false;
  const refreshed = await refreshDeviceToken(account.refresh_token);
  if (refreshed.status !== "ok" || !refreshed.access_token || !refreshed.refresh_token) return false;
  setDesktopCloudAccessToken(refreshed.access_token);
  await bridge.cloudAccountSave?.({
    ...account,
    refresh_token: refreshed.refresh_token,
    device_id: account.device_id,
  });
  const session = await createDesktopDataHubSession(account.device_id, refreshed.access_token);
  setDesktopDataHubSessionKey(session.plaintext);
  setDataMode("connected");
  return true;
}
