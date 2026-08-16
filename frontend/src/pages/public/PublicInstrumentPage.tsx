import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { BookmarkPlus, Monitor } from "lucide-react";
import { DataStatus, ErrorState, MetricStrip, Panel } from "@sigmx/ui";

import { cloudResearchApi, type PublicFundSummary, type PublicStockSummary } from "@/lib/cloudResearchApi";
import { isAuthenticated } from "@/lib/apiAuth";

function number(value: unknown, suffix = ""): string {
  return typeof value === "number" ? `${value.toLocaleString()}${suffix}` : "—";
}

export function PublicInstrumentPage({ kind }: { kind: "stock" | "fund" }) {
  const { code = "" } = useParams();
  const [data, setData] = useState<PublicStockSummary | PublicFundSummary | null>(null);
  const [error, setError] = useState("");
  const [handoffLink, setHandoffLink] = useState("");
  const [handoffError, setHandoffError] = useState("");
  const [watchlistState, setWatchlistState] = useState("");
  useEffect(() => { void (kind === "stock" ? cloudResearchApi.stock(code) : cloudResearchApi.fund(code)).then(setData).catch(reason => setError(reason instanceof Error ? reason.message : "加载失败")); }, [code, kind]);
  if (error) return <div className="mx-auto max-w-5xl px-4 py-12"><ErrorState title="未找到该标的" description={error} /></div>;
  if (!data) return <div role="status" className="page-state mx-auto my-12 max-w-5xl"><strong>正在加载行情、质量与研究上下文…</strong></div>;
  const stock = kind === "stock" ? data as PublicStockSummary : null;
  const fund = kind === "fund" ? data as PublicFundSummary : null;
  const quality = data.quality ?? {};

  const createHandoff = async () => {
    setHandoffError("");
    try { setHandoffLink((await cloudResearchApi.createHandoff("instrument", { symbol: data.code })).deep_link); }
    catch (reason) { setHandoffError(reason instanceof Error ? reason.message : "创建研究任务失败"); }
  };
  const addWatchlist = async () => {
    if (!isAuthenticated()) return;
    try { await cloudResearchApi.addWatchlist(data.code, data.name); setWatchlistState("已加入云自选"); }
    catch (reason) { setWatchlistState(reason instanceof Error ? reason.message : "加入失败"); }
  };

  const metrics = stock ? [
    { label: "收盘价", value: number(stock.close) },
    { label: "市盈率 TTM", value: number(stock.pe_ttm) },
    { label: "市净率", value: number(stock.pb) },
    { label: "股息率", value: number(stock.dividend_yield, "%") },
    { label: "ROE", value: number(stock.finance?.roe, "%") },
    { label: "每股收益", value: number(stock.finance?.eps) },
  ] : [
    { label: "最新价格", value: number(fund?.close) },
    { label: "涨跌幅", value: number(fund?.change_percent, "%"), change: number(fund?.change_percent, "%"), direction: (Number(fund?.change_percent ?? 0) >= 0 ? "up" : "down") as "up" | "down" },
    { label: "折溢价率", value: number(fund?.premium?.premium_rate, "%") },
    { label: "基金规模", value: number(fund?.scale?.total_size) },
    { label: "成交额", value: number(fund?.liquidity?.amount) },
    { label: "流动性", value: String(fund?.liquidity?.assessment ?? "—") },
  ];

  return <div className="mx-auto max-w-6xl space-y-5 px-4 py-8 sm:px-6">
    <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-5"><div><p className="text-xs uppercase tracking-[.18em] text-primary">{kind === "stock" ? "Equity Research" : "Fund Research"}</p><h1 className="mt-2 text-2xl font-semibold sm:text-3xl">{data.name} <code className="text-sm font-normal text-muted-foreground">{data.code}</code></h1><p className="mt-1 text-xs text-muted-foreground">{stock?.industry ?? fund?.fund_type ?? "—"}</p></div><div className="flex flex-wrap gap-2">{isAuthenticated() && <button type="button" onClick={() => void addWatchlist()} className="inline-flex items-center gap-2 rounded border px-3 py-2 text-xs"><BookmarkPlus className="h-3.5 w-3.5" />{watchlistState || "加入云自选"}</button>}<button type="button" onClick={() => void createHandoff()} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-2 text-xs font-medium text-primary-foreground"><Monitor className="h-3.5 w-3.5" />在 Desktop 中继续研究</button></div></header>
    <MetricStrip items={metrics} />
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(18rem,.75fr)]">
      <div className="space-y-5">
        <Panel title="研究摘要" description="基于当前公开数据生成的可验证摘要"><p className="text-sm leading-7">{data.research_summary}</p></Panel>
        {stock && <Panel title="资金动向" description="最近可用资金流记录">{stock.capital_flows.length ? <div className="divide-y">{stock.capital_flows.map((flow, index) => <div key={`${flow.trade_date}-${index}`} className="grid grid-cols-3 py-2 text-xs"><span>{String(flow.trade_date ?? "—")}</span><span className="font-mono">主力 {number(flow.main_net)}</span><span className="font-mono">散户 {number(flow.retail_net)}</span></div>)}</div> : <p className="text-xs text-muted-foreground">暂无资金流记录。</p>}</Panel>}
        {fund && <Panel title="折溢价与净值" description="场内价格相对净值状态"><div className="grid grid-cols-2 gap-4 text-sm"><div>净值 <strong className="ml-2 font-mono">{number(fund.premium?.nav)}</strong></div><div>折溢价 <strong className="ml-2 font-mono">{number(fund.premium?.premium_rate, "%")}</strong></div></div></Panel>}
        {fund && <Panel title="规模与流动性" description="成交承载和产品规模"><div className="grid grid-cols-2 gap-4 text-sm"><div>规模 <strong className="ml-2 font-mono">{number(fund.scale?.total_size)}</strong></div><div>成交额 <strong className="ml-2 font-mono">{number(fund.liquidity?.amount)}</strong></div></div></Panel>}
        {stock && <Panel title="近期事件" description="公告与重要事件">{stock.events.length ? <ol className="divide-y">{stock.events.map((event, index) => <li key={`${event.event_date}-${index}`} className="py-3"><div className="text-sm font-medium">{String(event.title)}</div><div className="mt-1 text-xs text-muted-foreground">{String(event.event_date ?? "—")} · {String(event.category ?? "事件")}</div></li>)}</ol> : <p className="text-xs text-muted-foreground">暂无近期事件。</p>}</Panel>}
      </div>
      <div className="space-y-5">
        <Panel title="风险与失效条件" description="研究结论需要持续验证"><ul className="space-y-2 text-xs leading-5">{data.risks.map(risk => <li key={risk} className="border-l-2 border-warning pl-2">{risk}</li>)}</ul></Panel>
        <Panel title="数据质量" description="来源、时间和校验状态"><DataStatus source={String(quality.source ?? data.source)} asOf={String(quality.updated_at ?? data.as_of ?? "") || null} freshness={data.is_delayed ? "延迟数据" : "实时"} quality={quality.status === "verified" ? "verified" : "degraded"} message={quality.status === "verified" ? undefined : "最新数据尚未完成全部质量校验"} /></Panel>
      </div>
    </div>
    <div className="rounded border bg-muted/15 p-4 text-xs text-muted-foreground">公开页面用于初步验证，不包含私有文件和完整回测。{!isAuthenticated() && <Link to="/login" state={{ from: `/${kind}/${code}` }} className="ml-2 font-medium text-primary">登录后保存并继续 →</Link>}{handoffLink && <span className="ml-3"><a href={handoffLink} className="font-medium text-primary">打开 Desktop</a><Link to="/download" className="ml-3 underline">下载 Desktop</Link></span>}{handoffError && <span role="alert" className="ml-3 text-destructive">{handoffError}</span>}</div>
  </div>;
}
