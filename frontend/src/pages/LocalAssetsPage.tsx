import { useEffect, useState } from "react";
import { Database, FileText, FolderArchive, HardDrive, LockKeyhole, Search } from "lucide-react";

import { getHarnessAssets, type LocalAssetsResponse } from "@/lib/harnessApi";

const KIND: Record<string, string> = { dataset: "数据集", research: "研究文件", report: "报告", cache: "缓存" };

export function LocalAssetsPage() {
  const [data, setData] = useState<LocalAssetsResponse | null>(null);
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getHarnessAssets({ kind: kind || undefined, query: query || undefined })
      .then(value => { if (active) { setData(value); setError(""); } })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "本地资产读取失败"); });
    return () => { active = false; };
  }, [kind, query]);

  return <div className="mx-auto max-w-[1400px] space-y-5 p-5 lg:p-7">
    <header><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Local-first workspace</p><h1 className="mt-1 text-2xl font-semibold">本地资产</h1><p className="mt-1 text-sm text-muted-foreground">管理本机数据集、研究文件、报告、缓存及其版本。文件内容不会上传到云端。</p></header>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Object.entries(KIND).map(([key, label]) => <button key={key} onClick={() => setKind(kind === key ? "" : key)} className={`rounded-lg border p-4 text-left transition-colors ${kind === key ? "border-primary bg-primary/5" : "bg-card hover:bg-muted/30"}`}><div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">{label}</span><AssetIcon kind={key} /></div><div className="mt-3 text-2xl font-semibold tabular-nums">{data?.summary.counts[key] ?? 0}</div></button>)}</div>
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3"><label className="flex min-w-64 flex-1 items-center gap-2 rounded-md border bg-background px-3"><Search className="h-4 w-4 text-muted-foreground" /><input aria-label="搜索本地资产" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索文件名或版本" className="h-9 w-full bg-transparent text-sm outline-none" /></label><div className="flex items-center gap-2 text-xs text-muted-foreground"><LockKeyhole className="h-3.5 w-3.5 text-success" />仅本机可见 · 共 {formatSize(data?.summary.total_size_bytes ?? 0)}</div></div>
    {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</div>}
    <div className="overflow-hidden rounded-lg border bg-card"><div className="grid grid-cols-[minmax(220px,1fr)_100px_130px_150px] border-b bg-muted/20 px-4 py-2 text-xs font-medium text-muted-foreground"><span>资产</span><span>类型</span><span>数据版本</span><span>大小 / 修改时间</span></div>{data?.items.map(item => <div key={item.id} className="grid grid-cols-[minmax(220px,1fr)_100px_130px_150px] items-center border-b px-4 py-3 text-sm last:border-b-0"><div className="flex min-w-0 items-center gap-3"><span className="rounded-md border bg-background p-2"><AssetIcon kind={item.kind} /></span><span className="truncate font-medium">{item.name}</span></div><span className="text-xs text-muted-foreground">{KIND[item.kind] || item.kind}</span><span className="text-xs">{item.version ? `版本 ${item.version}` : "未标记"}</span><span className="text-xs text-muted-foreground">{formatSize(item.size_bytes)} · {new Date(item.modified_at).toLocaleDateString("zh-CN")}</span></div>)}{data && data.items.length === 0 && <div className="p-10 text-center text-sm text-muted-foreground">暂无符合条件的本地资产</div>}</div>
  </div>;
}

function AssetIcon({ kind }: { kind: string }) { const Icon = kind === "dataset" ? Database : kind === "report" ? FileText : kind === "cache" ? FolderArchive : HardDrive; return <Icon className="h-4 w-4 text-primary" />; }
function formatSize(bytes: number) { if (bytes < 1024) return `${bytes} B`; if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`; return `${(bytes / 1024 ** 2).toFixed(1)} MB`; }
