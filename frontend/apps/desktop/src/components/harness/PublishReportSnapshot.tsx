import { useState } from "react";
import { ExternalLink, Share2, X } from "lucide-react";

import { cloudResearchApi, type CloudReport } from "@/lib/cloudResearchApi";

export function PublishReportSnapshot({ suggestedTitle }: { suggestedTitle: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(suggestedTitle.slice(0, 200));
  const [summary, setSummary] = useState("");
  const [published, setPublished] = useState<CloudReport | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const publish = async () => {
    if (!title.trim() || !summary.trim()) return;
    setSubmitting(true); setError("");
    try { setPublished(await cloudResearchApi.publishReport(title.trim(), summary.trim())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "发布失败"); }
    finally { setSubmitting(false); }
  };

  return <>
    <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"><Share2 className="h-3.5 w-3.5" />发布 Web 快照</button>
    {open && <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"><div className="w-full max-w-xl rounded-xl bg-background p-5 shadow-xl">
      <div className="flex items-start justify-between"><div><h2 className="font-semibold">发布脱敏报告快照</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">只会上传你在下方确认的标题和摘要；不会上传完整报告、本地文件、持仓、路径或密钥。</p></div><button aria-label="关闭" onClick={() => setOpen(false)}><X className="h-4 w-4" /></button></div>
      {published ? <div className="mt-5 rounded-md border border-success/30 bg-success/5 p-4 text-sm"><p className="font-medium">快照已发布，可随时在 Web 个人中心撤销。</p><a href={`/research/${published.slug}`} className="mt-3 inline-flex items-center gap-1 font-medium text-primary">打开公开快照<ExternalLink className="h-3.5 w-3.5" /></a></div> : <div className="mt-5 space-y-4">
        <label className="grid gap-1 text-sm">公开标题<input aria-label="公开标题" maxLength={200} value={title} onChange={event => setTitle(event.target.value)} className="rounded-md border bg-background px-3 py-2" /></label>
        <label className="grid gap-1 text-sm">脱敏摘要<textarea aria-label="脱敏摘要" maxLength={2000} rows={8} value={summary} onChange={event => setSummary(event.target.value)} placeholder="手动填写准备公开的结论、依据和风险。请删除个人持仓、文件名和任何敏感信息。" className="rounded-md border bg-background px-3 py-2" /><span className="text-right text-xs text-muted-foreground">{summary.length}/2000</span></label>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <button type="button" disabled={submitting || !title.trim() || !summary.trim()} onClick={() => void publish()} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-40">确认发布脱敏快照</button>
      </div>}
    </div></div>}
  </>;
}
