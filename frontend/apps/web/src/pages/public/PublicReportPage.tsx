import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { cloudResearchApi, PublicResearchError, type CloudReport } from "@/lib/cloudResearchApi";

export function PublicReportPage() {
  const { slug = "" } = useParams();
  const [report, setReport] = useState<CloudReport | null>(null);
  const [state, setState] = useState<"loading" | "revoked" | "missing" | "error">("loading");
  useEffect(() => { void cloudResearchApi.publicReport(slug).then((value) => { setReport(value); }).catch((reason) => setState(reason instanceof PublicResearchError && reason.status === 410 ? "revoked" : reason instanceof PublicResearchError && reason.status === 404 ? "missing" : "error")); }, [slug]);
  if (state === "revoked") return <Message title="该报告已被作者撤销" body="公开快照已失效，不会展示原报告内容。" />;
  if (state === "missing") return <Message title="未找到该报告" body="链接可能不完整或报告不存在。" />;
  if (state === "error") return <Message title="报告暂时不可用" body="请稍后重试。" />;
  if (!report) return <div className="mx-auto max-w-3xl px-4 py-16 text-muted-foreground">正在加载报告快照…</div>;
  return <article className="mx-auto max-w-3xl px-4 py-12"><p className="text-xs uppercase tracking-widest text-primary">用户主动公开 · 脱敏快照</p><h1 className="mt-3 text-3xl font-bold">{report.title}</h1><p className="mt-2 text-xs text-muted-foreground">发布于 {new Date(report.created_at).toLocaleString()}</p><div className="mt-8 whitespace-pre-wrap rounded-xl border bg-card p-6 leading-7">{report.summary}</div><p className="mt-6 text-xs text-muted-foreground">该快照仅供研究参考，不构成投资建议。</p></article>;
}

function Message({ title, body }: { title: string; body: string }) { return <div className="mx-auto max-w-3xl px-4 py-20"><h1 className="text-2xl font-bold">{title}</h1><p className="mt-3 text-muted-foreground">{body}</p></div>; }
