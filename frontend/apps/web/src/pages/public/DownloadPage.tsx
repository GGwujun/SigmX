/**
 * Download page (design §7.1 /download): server-driven stable release info.
 * GET /api/catalog/releases/stable — version/notes/download_url come from the
 * server, never hard-coded (plan Global Constraints).
 */
import { useEffect, useState } from "react";
import { Download, Loader2, AlertCircle } from "lucide-react";

import { ApiError } from "@/lib/api";
import { getStableRelease, type StableRelease } from "@/lib/productApi";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

export function DownloadPage() {
  const [release, setRelease] = useState<StableRelease | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getStableRelease();
        if (!cancelled) setRelease(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "无法加载版本信息");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight">下载客户端</h1>
      <p className="mt-2 text-muted-foreground">服务端驱动的稳定版本信息。</p>

      {loading ? (
        <div className="mt-10 flex items-center text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> 加载版本信息…
        </div>
      ) : error ? (
        <div className="mt-10 flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      ) : (
        <section className="mt-10 rounded-2xl border bg-card p-8">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Download className="h-5 w-5 text-primary" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">当前稳定版</div>
              <div className="text-2xl font-bold">v{release?.version ?? "—"}</div>
            </div>
          </div>

          {release?.notes && (
            <p className="mt-4 whitespace-pre-line text-sm text-muted-foreground">
              {release.notes}
            </p>
          )}

          {release?.download_url ? (
            <a
              href={release.download_url}
              onClick={() => trackPersonalFunnel("download_clicked")}
              className="mt-6 inline-flex h-11 items-center gap-2 rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <Download className="h-4 w-4" /> 下载 v{release.version}
            </a>
          ) : (
            <p className="mt-6 text-sm text-muted-foreground">暂无可用下载链接。</p>
          )}
        </section>
      )}
    </div>
  );
}
