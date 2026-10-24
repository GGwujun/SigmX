import { type ReactNode, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, Menu, Search, SquarePen, X } from "lucide-react";
import type { ResearchTask } from "@/lib/researchApi";
import { getUser, isAuthenticated } from "@/lib/apiAuth";
import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AccountMenu } from "@/components/navigation/AccountMenu";
import { publicNavItems } from "@/components/public/publicNav";

interface Props { recentTasks: ResearchTask[]; activeTaskId: string | null; onNewAnalysis: () => void; children: ReactNode }
const isToday = (value: string) => new Date(value).toDateString() === new Date().toDateString();

function HistoryList({ tasks, query, activeTaskId, onSelect }: { tasks: ResearchTask[]; query: string; activeTaskId: string | null; onSelect?: () => void }) {
  const groups = useMemo(() => {
    // Retries of the same question produce many identical rows — keep the newest one.
    const unique = tasks.filter((item, index, all) => all.findIndex(other => other.question === item.question) === index);
    const matched = query.trim() ? unique.filter(item => item.question.toLowerCase().includes(query.trim().toLowerCase())) : unique;
    return { today: matched.filter(item => isToday(item.created_at)), earlier: matched.filter(item => !isToday(item.created_at)) };
  }, [tasks, query]);
  if (!tasks.length) return <p className="px-2.5 py-6 text-[13px] leading-5 text-[#8f8f8f]">还没有分析记录，开始一次分析后会显示在这里。</p>;
  if (query.trim() && !groups.today.length && !groups.earlier.length) return <p className="px-2.5 py-4 text-[13px] text-[#8f8f8f]">没有匹配的对话</p>;
  const group = (label: string, items: ResearchTask[]) => items.length ? <section className="mt-3"><h3 className="px-2.5 text-[11px] font-medium text-[#8f8f8f]">{label}</h3><div className="mt-0.5 space-y-0.5">{items.map(item => <Link key={item.id} to={`/?conversation=${item.id}`} aria-label={item.question} aria-current={item.id === activeTaskId ? "page" : undefined} onClick={onSelect} className={`block truncate rounded-lg px-2.5 py-[7px] text-[13px] leading-5 transition-colors ${item.id === activeTaskId ? "bg-[#ececec] font-medium text-[#0d0d0d]" : "text-[#3d3d3d] hover:bg-[#f0f0f0] hover:text-[#0d0d0d]"}`}>{item.question}</Link>)}</div></section> : null;
  return <>{group("今天", groups.today)}{group("更早", groups.earlier)}</>;
}

// ChatGPT 式浅色侧栏（与用户截图逐项对齐）：顶行=品牌+搜索图标钮；
// 新建分析与产品导航全部一级 icon 行（无分组标签）；「对话历史」小灰字分组；
// 底部头像账号行。白底近无彩色，active 为浅灰圆角底。
function Sidebar({ recentTasks, activeTaskId, onNewAnalysis, onClose }: Omit<Props, "children"> & { onClose?: () => void }) {
  const { pathname } = useLocation();
  const items = publicNavItems(pathname);
  const user = isAuthenticated() ? getUser() : null;
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [historyOpen, setHistoryOpen] = useState(true);
  // 截图微细节：普通行文字 #353540 偏深、hover 是更轻的 #f0f0f0 圆角 8px、active 浅灰 #ececec。
  const rowClass = (active: boolean) => `flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[14px] transition-colors ${active ? "bg-[#ececec] font-medium text-[#0d0d0d]" : "text-[#3d3d3d] hover:bg-[#f0f0f0] hover:text-[#0d0d0d]"}`;
  return <div className="flex h-full flex-col bg-[#f9f9f9]">
    <div className="flex shrink-0 items-center justify-between px-3 pb-1.5 pt-3">
      <Link to="/" className="flex items-center gap-2 rounded-lg px-1.5 py-1 text-[15px] font-semibold text-[#0d0d0d]"><SigmXLogo className="h-[22px] w-[22px]" />SigmX</Link>
      <div className="flex items-center gap-0.5">
        <button type="button" aria-label={searchOpen ? "关闭搜索" : "搜索对话"} aria-pressed={searchOpen} onClick={() => { setSearchOpen(value => !value); if (searchOpen) setQuery(""); }} className={`grid h-9 w-9 place-items-center rounded-lg transition-colors ${searchOpen ? "bg-[#ececec] text-[#0d0d0d]" : "text-[#5d5d5d] hover:bg-[#ececec]/60 hover:text-[#0d0d0d]"}`}><Search className="h-[18px] w-[18px] stroke-[1.8]" /></button>
        {onClose && <button type="button" aria-label="关闭菜单" onClick={onClose} className="grid h-9 w-9 place-items-center rounded-lg text-[#5d5d5d] transition-colors hover:bg-[#ececec]/60 hover:text-[#0d0d0d]"><X className="h-[18px] w-[18px]" /></button>}
      </div>
    </div>
    {searchOpen && <div className="px-3 pb-2"><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索对话" className="h-9 w-full rounded-lg border border-[#e0e0e0] bg-white px-3 text-[13px] text-[#0d0d0d] outline-none placeholder:text-[#8f8f8f] focus:border-[#c9c9c9]" /></div>}
    <nav aria-label="产品导航" className="px-2">
      <button type="button" onClick={() => { onNewAnalysis(); onClose?.(); }} className={`${rowClass(false)} w-full`}><SquarePen className="h-[17px] w-[17px] shrink-0 stroke-[1.7]" />新建分析</button>
      <div className="mt-0.5 space-y-0.5">{items.map(item => <Link key={item.to} to={item.to} aria-current={item.active ? "page" : undefined} onClick={onClose} className={rowClass(item.active)}><item.icon className="h-[17px] w-[17px] shrink-0 stroke-[1.7]" />{item.label}</Link>)}</div>
    </nav>
    <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
      {/* 截图「项目」小标题带 chevron 可折叠；外层 h2 保住 heading 语义（契约测试）。搜索过滤时强制展开。 */}
      <h2 className="mt-4"><button type="button" aria-expanded={historyOpen} onClick={() => setHistoryOpen(value => !value)} className="flex w-full items-center gap-1 rounded-md px-2.5 py-1 text-[12px] font-medium text-[#8f8f8f] transition-colors hover:text-[#5d5d5d]">对话历史<ChevronDown aria-hidden="true" className={`h-3 w-3 transition-transform duration-200 ${historyOpen ? "" : "-rotate-90"}`} /></button></h2>
      {(historyOpen || query.trim()) && <HistoryList tasks={recentTasks} query={query} activeTaskId={activeTaskId} onSelect={onClose} />}
    </div>
    <div className="shrink-0 border-t border-[#ececec] p-2">
      {user ? <AccountMenu user={user} align="left" /> : <div className="flex items-center gap-2 px-0.5"><Link to="/login" className="flex h-8 flex-1 items-center justify-center rounded-full border border-[#d9d9e3] text-[13px] font-medium text-[#0d0d0d] transition-colors hover:bg-[#f3f3f3]">登录</Link><Link to="/register" className="flex h-8 flex-1 items-center justify-center rounded-full bg-[#0d0d0d] text-[13px] font-medium text-white transition-opacity hover:opacity-90">注册体验</Link></div>}
    </div>
  </div>;
}

export function AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children }: Props) {
  const [open, setOpen] = useState(false);
  // ChatGPT 式布局（与用户截图完全对齐）：左栏从视口顶铺到底，承载品牌/搜索/
  // 一级功能行/对话历史/账号——整页没有横贯顶栏；右栏是一整块纯聊天表面。
  return <div className="aiw"><div data-testid="analysis-workspace" className="flex h-dvh min-h-[600px] overflow-hidden lg:grid lg:grid-cols-[288px_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)]">
    <aside className="hidden border-r border-[#ececec] bg-[#f9f9f9] lg:col-start-1 lg:row-start-1 lg:block"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} /></aside>
    <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white lg:col-start-2 lg:row-start-1"><button type="button" aria-label="打开菜单" onClick={() => setOpen(true)} className="absolute left-3 top-3 z-10 grid h-9 w-9 place-items-center rounded-full border border-black/10 bg-white text-[#0d0d0d] shadow-md transition-colors hover:bg-[#f7f7f7] lg:hidden"><Menu className="h-[18px] w-[18px]" /></button>{children}</section>
  </div>{open && <div className="fixed inset-0 z-50 lg:hidden"><button type="button" aria-label="关闭菜单遮罩" onClick={() => setOpen(false)} className="absolute inset-0 bg-black/40" /><aside className="relative h-full w-[min(84vw,300px)] border-r border-[#ececec] bg-[#f9f9f9] shadow-2xl"><Sidebar recentTasks={recentTasks} activeTaskId={activeTaskId} onNewAnalysis={onNewAnalysis} onClose={() => setOpen(false)} /></aside></div>}</div>;
}
