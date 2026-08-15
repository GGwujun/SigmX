import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cloudResearchApi, type PublicFundSummary, type PublicStockSummary } from "@/lib/cloudResearchApi";
import { isAuthenticated } from "@/lib/apiAuth";

export function PublicInstrumentPage({ kind }: { kind: "stock" | "fund" }) {
  const { code = "" } = useParams();
  const [data, setData] = useState<PublicStockSummary | PublicFundSummary | null>(null);
  const [error, setError] = useState("");
  const [handoffLink, setHandoffLink] = useState("");
  const [handoffError, setHandoffError] = useState("");
  useEffect(() => { void (kind === "stock" ? cloudResearchApi.stock(code) : cloudResearchApi.fund(code)).then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "加载失败")); }, [code, kind]);
  if (error) return <div className="mx-auto max-w-4xl px-4 py-16"><h1 className="text-2xl font-bold">未找到该标的</h1><p className="mt-2 text-muted-foreground">{error}</p></div>;
  if (!data) return <div className="mx-auto max-w-4xl px-4 py-16 text-muted-foreground">正在加载延迟行情…</div>;
  const stock = kind === "stock" ? data as PublicStockSummary : null;
  const fund = kind === "fund" ? data as PublicFundSummary : null;
  const createHandoff = async () => {
    setHandoffError("");
    try { setHandoffLink((await cloudResearchApi.createHandoff("instrument", { symbol: data.code })).deep_link); }
    catch (reason) { setHandoffError(reason instanceof Error ? reason.message : "创建研究任务失败"); }
  };
  return <div className="mx-auto max-w-4xl space-y-6 px-4 py-12"><header><p className="text-xs uppercase tracking-widest text-primary">{kind === "stock" ? "股票简析" : "基金概览"}</p><h1 className="mt-2 text-3xl font-bold">{data.name} <code className="text-base font-normal text-muted-foreground">{data.code}</code></h1><p className="mt-2 text-sm text-muted-foreground">延迟数据 · 截至 {data.as_of ?? "暂无行情"} · 来源 {data.source}</p></header><section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="收盘价" value={data.close?.toLocaleString() ?? "—"} />{stock && <><Metric label="市盈率 TTM" value={stock.pe_ttm?.toString() ?? "—"} /><Metric label="市净率" value={stock.pb?.toString() ?? "—"} /><Metric label="股息率" value={stock.dividend_yield == null ? "—" : `${stock.dividend_yield}%`} /></>}{fund && <><Metric label="类型" value={fund.fund_type ?? "—"} /><Metric label="涨跌幅" value={fund.change_percent == null ? "—" : `${fund.change_percent}%`} /></>}</section><div className="rounded-xl border bg-muted/20 p-5 text-sm"><p>这里提供公开的轻量验证，不包含完整回测、私有文件或持续监控。</p>{isAuthenticated() ? <button type="button" onClick={() => void createHandoff()} className="mt-3 font-medium text-primary">在 Desktop 中继续研究</button> : <Link to="/login" state={{ from: `/stock/${code}` }} className="mt-3 inline-block font-medium text-primary">登录后在 Desktop 继续 →</Link>}{handoffLink && <div className="mt-3 flex gap-3"><a href={handoffLink} className="font-medium text-primary">打开 Desktop</a><Link to="/download" className="text-muted-foreground underline">下载 Desktop</Link></div>}{handoffError && <p role="alert" className="mt-2 text-destructive">{handoffError}</p>}</div></div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border bg-card p-4"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-2 text-xl font-semibold">{value}</div></div>; }
