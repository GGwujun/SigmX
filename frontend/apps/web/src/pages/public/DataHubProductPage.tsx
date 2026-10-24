import { ArrowRight, Bot, CheckCircle2, Code2, Database, FileSearch, Gauge, KeyRound, LineChart, ShieldCheck, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

const DOMAINS = [["行情与估值", "股票、指数、基金、复权行情与估值分位", LineChart], ["财务与基本面", "三大报表、财务指标、盈利预测与公司资料", Database], ["公告与情报", "交易所公告、财经新闻、政策与产业链事件", FileSearch], ["资金与市场行为", "资金流、龙虎榜、融资融券与机构持仓", Gauge]] as const;

/** 产品页与聊天工作台同一套视觉语言（白底、zinc 灰阶、黑主按钮、
 * emerald 仅作完成态点缀），不再使用旧的暗色科技风。 */
export function DataHubProductPage() {
  return <div className="bg-white text-zinc-950">
    <section className="border-b border-zinc-100"><div className="mx-auto grid max-w-[1200px] gap-10 px-5 py-12 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:gap-12 lg:py-16">
      <div>
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-zinc-400">SigmX Data Hub</p>
        <h1 className="mt-4 text-[28px] font-semibold leading-[1.25] tracking-[-0.035em] sm:text-[32px]">让 AI 智能体直接使用<br /><span className="text-emerald-600">可信的金融数据</span></h1>
        <p className="mt-5 max-w-xl text-[14px] leading-7 text-zinc-500">统一接入行情、财务、公告、新闻、资金与产业数据。无论是本地 AI 智能体、投研 Skills，还是你自己的分析程序，都通过同一套标准接口获得可追溯的数据。</p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/account/data-hub" className="inline-flex h-11 items-center gap-2 rounded-xl bg-zinc-950 px-5 text-[13.5px] font-medium text-white transition-colors hover:bg-zinc-800">进入控制台 <ArrowRight className="h-4 w-4" /></Link>
          <Link to="/docs/data-hub/" className="inline-flex h-11 items-center gap-2 rounded-xl border border-zinc-200 px-5 text-[13.5px] font-medium text-zinc-950 transition-colors hover:bg-zinc-50">查看 API 文档 <Code2 className="h-4 w-4 text-zinc-500" /></Link>
        </div>
        <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-zinc-500">{["按量计费", "Credential 独立管理", "来源与时间戳可追溯"].map((item) => <span key={item} className="inline-flex items-center gap-1.5"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />{item}</span>)}</div>
      </div>
      <div className="rounded-2xl border border-zinc-200 bg-zinc-50/60 p-5">
        <div className="flex items-center justify-between border-b border-zinc-200 pb-4"><div className="flex items-center gap-2 text-[13.5px] font-semibold"><Bot className="h-4 w-4 text-zinc-600" />本地智能体调用</div><span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">200 OK · 86ms</span></div>
        <pre className="mt-5 overflow-x-auto font-mono text-[12.5px] leading-7 text-zinc-700"><code>{`from sigmx import DataHub\n\nhub = DataHub()\nresult = hub.query(\n  "现金流连续改善且估值低于历史中位数"\n)\n\nprint(result.evidence)`}</code></pre>
        <div className="mt-5 grid grid-cols-3 gap-2">{[["数据域", "6"], ["标准接口", "300+"], ["质量监控", "持续"]].map(([label, value]) => <div key={label} className="rounded-xl border border-zinc-200 bg-white p-3"><div className="text-[11px] text-zinc-400">{label}</div><div className="mt-1 text-[16px] font-semibold tabular-nums text-zinc-950">{value}</div></div>)}</div>
      </div>
    </div></section>

    <section className="mx-auto max-w-[1200px] px-5 py-12 sm:px-8 lg:py-16"><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-zinc-400">数据覆盖</p><h2 className="mt-3 text-[22px] font-semibold tracking-[-0.03em] sm:text-[24px]">一套接口，覆盖完整研究证据</h2><p className="mt-3 max-w-2xl text-[13.5px] leading-7 text-zinc-500">Data Hub 不是另一个选股页面，而是 Web 投研、投研 Skills 和本地智能体背后的数据基础设施。</p><div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{DOMAINS.map(([title, description, Icon]) => <div key={title} className="rounded-2xl border border-zinc-200 p-5 transition-colors hover:border-zinc-300"><Icon className="h-5 w-5 text-zinc-600" /><h3 className="mt-4 text-[15px] font-semibold">{title}</h3><p className="mt-2 text-[13px] leading-6 text-zinc-500">{description}</p></div>)}</div></section>

    <section className="border-y border-zinc-100 bg-zinc-50/50"><div className="mx-auto grid max-w-[1200px] gap-8 px-5 py-12 sm:px-8 lg:grid-cols-3 lg:py-16"><Step icon={KeyRound} title="1. 创建 Credential">在账户控制台创建独立密钥，按智能体或项目隔离。</Step><Step icon={Sparkles} title="2. 安装 Skill 或 SDK">把官方投研 Skill 安装到 Codex、Claude Code 等本地助手。</Step><Step icon={ShieldCheck} title="3. 获取可验证结论">接口返回数据状态、来源和时间戳，便于复核研究过程。</Step></div></section>

    <section className="mx-auto max-w-[900px] px-5 py-14 text-center sm:px-8 lg:py-20"><h2 className="text-[22px] font-semibold tracking-[-0.03em] sm:text-[24px]">让你的 AI 从可靠数据开始研究</h2><p className="mx-auto mt-4 max-w-2xl text-[13.5px] leading-7 text-zinc-500">先在 Skills 广场体验研究方法，再按需要开通 Data Hub Credential。</p><div className="mt-7 flex flex-wrap justify-center gap-3"><Link to="/skills" className="inline-flex h-11 items-center rounded-xl border border-zinc-200 px-5 text-[13.5px] font-medium text-zinc-950 transition-colors hover:bg-zinc-50">浏览投研 Skills</Link><Link to="/account/data-hub" className="inline-flex h-11 items-center rounded-xl bg-zinc-950 px-5 text-[13.5px] font-medium text-white transition-colors hover:bg-zinc-800">开通 Data Hub</Link></div></section>
  </div>;
}

function Step({ icon: Icon, title, children }: { icon: typeof KeyRound; title: string; children: string }) { return <div><Icon className="h-5 w-5 text-zinc-600" /><h3 className="mt-3.5 text-[15.5px] font-semibold">{title}</h3><p className="mt-2 text-[13px] leading-6 text-zinc-500">{children}</p></div>; }
