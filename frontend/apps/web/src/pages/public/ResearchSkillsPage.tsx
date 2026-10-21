import { useEffect, useMemo, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, BarChart3, BookOpenCheck, Building2, FileCheck2, Landmark, LoaderCircle, Search, Users } from "lucide-react";
import { getSkills, type PublicSkill } from "@/lib/skillsApi";

const tabs = ["推荐", "选股", "基本面", "行业", "宏观"];
const icons: ComponentType<{ className?: string }>[] = [BarChart3, FileCheck2, Building2, Landmark, BookOpenCheck];

export function ResearchSkillsPage() {
  const [skills, setSkills] = useState<PublicSkill[]>([]);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState("推荐");
  const [visibleCount, setVisibleCount] = useState(12);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { getSkills().then(setSkills).catch(cause => setError(cause instanceof Error ? cause.message : "技能目录不可用")).finally(() => setLoading(false)); }, []);
  const filtered = useMemo(() => skills.filter(skill => {
    const text = `${skill.name} ${skill.description} ${skill.slug} ${skill.ownership_label} ${skill.primary_source_label}`.toLowerCase();
    const matchesQuery = text.includes(query.trim().toLowerCase());
    const matchesTab = tab === "推荐" || (tab === "选股" && /选股|筛选|stock|factor|dividend/.test(text)) || (tab === "基本面" && /基本面|财务|估值|fundamental|valuation|financial/.test(text)) || (tab === "行业" && /行业|板块|产业|sector|industry/.test(text)) || (tab === "宏观" && /宏观|利率|货币|经济|macro|econom/.test(text));
    return matchesQuery && matchesTab;
  }), [skills, query, tab]);
  const featured = filtered.slice(0, 2);
  const catalogSkills = filtered.slice(featured.length);

  return <div className="bg-white text-zinc-950">
    <main className="mx-auto max-w-[1440px] px-5 py-6 sm:px-8 lg:px-10 lg:py-7">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><h1 className="text-[24px] font-semibold tracking-[-0.035em]">投研 Skills</h1><p className="mt-1 text-[13px] text-zinc-500">把专业研究方法变成可复用的分析能力</p></div><label className="relative block w-full md:w-[420px]"><Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"/><input aria-label="搜索投研 Skills" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索 Skills" className="h-10 w-full rounded-xl border border-zinc-200 bg-zinc-50/50 pl-10 pr-4 text-[13px] outline-none transition focus:border-zinc-400 focus:bg-white focus:ring-4 focus:ring-zinc-100"/></label></header>
      <nav aria-label="技能分类" className="mt-4 flex gap-7 overflow-x-auto border-b border-zinc-200">{tabs.map(item => <button key={item} type="button" onClick={() => setTab(item)} aria-current={tab === item ? "page" : undefined} className={`relative shrink-0 px-1 pb-2.5 text-[12px] transition ${tab === item ? "font-semibold text-zinc-950 after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-zinc-950" : "text-zinc-500 hover:text-zinc-900"}`}>{item}</button>)}</nav>
      {loading && <div className="flex justify-center gap-2 py-24 text-sm text-zinc-500"><LoaderCircle className="h-5 w-5 animate-spin"/>正在读取技能目录</div>}
      {error && <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {!loading && !error && <>
        {featured.length > 0 && <section className="mt-7"><h2 className="text-[17px] font-semibold tracking-[-0.02em]">常用 Skills</h2><div className="mt-3 grid gap-4 lg:grid-cols-2">{featured.map((skill, index) => <FeaturedSkill key={skill.slug} skill={skill} icon={icons[index % icons.length]} />)}</div></section>}
        <section className="mt-8"><div className="flex items-end justify-between"><h2 className="text-[17px] font-semibold tracking-[-0.02em]">全部 Skills</h2><span className="text-[12px] text-zinc-500">{filtered.length} 个已发布技能</span></div>
          <div data-testid="research-skills-grid" className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{catalogSkills.slice(0, visibleCount).map((skill, index) => <SkillCard key={skill.slug} skill={skill} icon={icons[(index + featured.length) % icons.length]} />)}</div>
          {visibleCount < catalogSkills.length && <div className="mt-6 flex justify-center"><button type="button" onClick={() => setVisibleCount(count => count + 12)} className="rounded-xl border border-zinc-300 px-5 py-2.5 text-[13px] font-medium text-zinc-700 transition hover:bg-zinc-50">加载更多 Skills</button></div>}
          {filtered.length === 0 && <div className="mt-4 rounded-xl border border-dashed border-zinc-200 py-16 text-center text-sm text-zinc-500">没有匹配的已发布 Skill</div>}
        </section>
      </>}
    </main>
  </div>;
}

function FeaturedSkill({ skill, icon: Icon }: { skill: PublicSkill; icon: ComponentType<{ className?: string }> }) {
  return <Link to={`/skills/${skill.slug}`} aria-label={`${skill.name} 查看详情`} className="group grid min-h-40 grid-cols-[52px_minmax(0,1fr)] gap-4 rounded-2xl border border-zinc-200 p-5 transition hover:border-zinc-300 hover:shadow-[0_8px_28px_rgba(0,0,0,.05)] sm:grid-cols-[64px_minmax(0,1fr)_auto] sm:items-center"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-800"><Icon className="h-7 w-7 stroke-[1.5]"/></span><div><h3 className="font-semibold tracking-[-0.01em]">{skill.name}</h3><p className="mt-1.5 line-clamp-2 text-[13px] leading-5 text-zinc-500">{skill.description || "请进入详情查看技能说明。"}</p><SkillTags skill={skill}/></div><span className="col-start-2 inline-flex w-fit items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-2 text-xs font-medium text-zinc-800 group-hover:bg-zinc-950 group-hover:text-white sm:col-start-auto">开始分析 <ArrowRight className="h-3.5 w-3.5"/></span></Link>;
}

function SkillCard({ skill, icon: Icon }: { skill: PublicSkill; icon: ComponentType<{ className?: string }> }) {
  return <Link data-testid="research-skill-card" to={`/skills/${skill.slug}`} aria-label={`${skill.name} 查看详情`} className="group flex min-h-48 flex-col rounded-2xl border border-zinc-200 p-5 transition hover:border-zinc-300 hover:shadow-[0_8px_28px_rgba(0,0,0,.05)]"><div className="flex items-start gap-4"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-800"><Icon className="h-6 w-6 stroke-[1.5]"/></span><div><h3 className="font-semibold tracking-[-0.01em] group-hover:text-zinc-700">{skill.name}</h3><p className="mt-1.5 line-clamp-2 text-[13px] leading-5 text-zinc-500">{skill.description || "请进入详情查看技能说明。"}</p></div></div><SkillTags skill={skill}/><div className="mt-auto flex items-center gap-1.5 pt-4 text-[11px] text-zinc-400"><Users className="h-3.5 w-3.5"/>{skill.execution === "executable" ? "可直接运行" : "方法指南"}</div></Link>;
}

function SkillTags({ skill }: { skill: PublicSkill }) { return <div className="mt-3 flex flex-wrap gap-1.5"><span className="rounded-md border border-zinc-200 px-2 py-1 text-[10px] text-zinc-500">{skill.ownership_label}</span><span className="rounded-md border border-zinc-200 px-2 py-1 text-[10px] text-zinc-500">{skill.primary_source_label}</span><span className="rounded-md border border-zinc-200 px-2 py-1 text-[10px] text-zinc-500">{skill.execution === "executable" ? "可执行" : "方法指南"}</span></div>; }
