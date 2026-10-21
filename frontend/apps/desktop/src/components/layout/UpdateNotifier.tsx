/**
 * UpdateNotifier — shows desktop auto-update status in the app shell.
 *
 * Listens to sigmxDesktop IPC events from the Electron main process:
 *  - update-available   → "发现 vX，正在下载..." + progress bar
 *  - update-progress    → percentage + speed
 *  - update-downloaded  → "下载完成，重启后安装" + restart button
 *  - update-not-available → silent (no-op)
 *  - update-error       → toast the error
 */

import { useEffect, useState } from "react";
import { Download, CheckCircle, X } from "lucide-react";

// NOTE: the global Window.sigmxDesktop type is declared in useAuthState.ts.
// We rely on that rather than redeclaring to avoid TS2717 conflicts.

interface UpdateProgress {
  percent: number;
  transferred: number;
  total: number;
  bytesPerSecond: number;
}

type UpdatePhase = "idle" | "downloading" | "downloaded" | "restarting";

function fmtSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtSpeed(bytesPerSec: number) {
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(0)} KB/s`;
  return `${(bytesPerSec / (1024 * 1024)).toFixed(1)} MB/s`;
}

export default function UpdateNotifier() {
  const [phase, setPhase] = useState<UpdatePhase>("idle");
  const [version, setVersion] = useState("");
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const isDesktop = typeof window !== "undefined" && !!window.sigmxDesktop?.isDesktop;
  const showBanner = phase !== "idle" && !dismissed;

  useEffect(() => {
    if (!isDesktop) return;
    const s = window.sigmxDesktop!;

    const unsubs: (() => void)[] = [];

    unsubs.push(
      s.onUpdateAvailable?.((info) => {
        setVersion(info.version);
        setPhase("downloading");
        setDismissed(false);
      }) ?? (() => {})
    );

    unsubs.push(
      s.onUpdateProgress?.((p) => {
        setProgress({ ...p }); // shallow copy to trigger re-render
        if (phase === "idle") setPhase("downloading");
      }) ?? (() => {})
    );

    unsubs.push(
      s.onUpdateDownloaded?.((info) => {
        setVersion(info.version);
        setProgress(null);
        setPhase("downloaded");
        setDismissed(false);
      }) ?? (() => {})
    );

    unsubs.push(
      s.onUpdateNotAvailable?.(() => {
        // No update — stay idle. The menu dialog already told the user.
      }) ?? (() => {})
    );

    unsubs.push(
      s.onUpdateError?.((err) => {
        console.warn("[sigmx] update error:", err.message);
        setPhase("idle");
      }) ?? (() => {})
    );

    return () => unsubs.forEach((fn) => fn());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDesktop]);

  function handleRestart() {
    setPhase("restarting");
    window.sigmxDesktop?.quitAndInstall?.();
  }

  if (!isDesktop || !showBanner) return null;

  return (
    <div className="border-b bg-primary/5 px-4 py-2">
      {phase === "downloading" && (
        <div className="flex items-center gap-3">
          <Download className="h-4 w-4 shrink-0 animate-pulse text-primary" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium">
              正在下载 SigmX {version}
              {progress && (
                <span className="ml-2 font-normal text-muted-foreground">
                  {progress.percent}% · {fmtSpeed(progress.bytesPerSecond)}
                </span>
              )}
            </p>
            {progress && (
              <div className="mt-1 h-1.5 w-full rounded-full bg-muted">
                <div
                  className="h-1.5 rounded-full bg-primary transition-all duration-300"
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
            )}
            {progress && (
              <p className="mt-0.5 text-[10px] text-muted-foreground">
                {fmtSize(progress.transferred)} / {fmtSize(progress.total)}
              </p>
            )}
          </div>
          <button
            onClick={() => setDismissed(true)}
            className="shrink-0 rounded p-0.5 hover:bg-muted"
            aria-label="隐藏"
          >
            <X className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      )}

      {phase === "downloaded" && (
        <div className="flex items-center gap-3">
          <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium">
              SigmX {version} 已下载，重启后自动安装
            </p>
          </div>
          <button
            onClick={handleRestart}
            className="shrink-0 rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            立即重启
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="shrink-0 rounded p-0.5 hover:bg-muted"
            aria-label="隐藏"
          >
            <X className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      )}

      {phase === "restarting" && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Download className="h-3.5 w-3.5 animate-pulse" />
          正在重启以完成更新...
        </div>
      )}
    </div>
  );
}
