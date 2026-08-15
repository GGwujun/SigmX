/**
 * Public acquisition homepage (design §7.1 `/`): brand value, the three product
 * shapes (website / Data Hub / desktop), and primary CTAs. Static content — no
 * API calls — so it renders fast and never breaks on a catalog outage.
 */
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, Database, Monitor, ArrowRight, Globe2 } from "lucide-react";
import { trackPersonalFunnel } from "@/lib/personalFunnel";

const PRODUCTS = [
  {
    icon: Globe2,
    name: "SigmX Web",
    desc: "无需安装即可搜索股票、基金与自然语言条件，完成轻量验证并保存到个人云空间。",
    href: "/query/%E4%BD%8E%E4%BC%B0%E5%80%BC%20%E9%AB%98%E8%82%A1%E6%81%AF",
    cta: "体验 AI 选股",
  },
  {
    icon: Monitor,
    name: "桌面客户端",
    desc: "本地持仓、自选、回测与定时任务。Standalone 模式本地运行，Connected 模式连接 Data Hub。",
    href: "/product/desktop",
    cta: "了解桌面端",
  },
  {
    icon: Database,
    name: "Data Hub",
    desc: "标准化金融数据 API，可独立于 Desktop 使用；按接口权限和 Data Credit 精确计量。",
    href: "/product/data-hub",
    cta: "了解 Data Hub",
  },
];

const HIGHLIGHTS = [
  "产品分离、平台能力共享：统一账号、数据集、指标与权益",
  "激活码开通套餐，权益与积分立即生效",
  "Standalone 离线可用，云端不可达时本地功能不中断",
];

export function LandingPage() {
  useEffect(() => trackPersonalFunnel("landing_view"), []);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = query.trim();
    if (value) navigate(`/query/${encodeURIComponent(value)}`);
  };
  return (
    <div>
      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          面向中国 A 股的
          <span className="text-primary"> 投研数据与 AI</span>
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-muted-foreground">
          多源降级采集的行情/基本面/资金流数据，可运营的套餐与积分体系，以及本地优先的桌面客户端。
        </p>
        <form onSubmit={submit} className="mx-auto mt-8 flex max-w-2xl gap-2 rounded-xl border bg-card p-2 shadow-sm">
          <label className="sr-only" htmlFor="public-search">统一搜索</label>
          <Search className="ml-2 mt-2.5 h-5 w-5 text-muted-foreground" />
          <input id="public-search" aria-label="统一搜索" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入代码、名称，或试试：低估值 高股息 小市值" className="min-w-0 flex-1 bg-transparent px-2 text-sm outline-none" />
          <button type="submit" className="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground">开始查询</button>
        </form>
        <div className="mt-4 flex items-center justify-center gap-3">
          <Link
            to="/register"
            className="inline-flex h-11 items-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            免费注册
          </Link>
          <Link
            to="/pricing"
            className="inline-flex h-11 items-center gap-1 rounded-md border px-6 text-sm font-medium hover:bg-muted"
          >
            查看套餐 <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* Highlights */}
      <section className="border-y bg-muted/30">
        <div className="mx-auto grid max-w-6xl gap-4 px-4 py-8 sm:grid-cols-3">
          {HIGHLIGHTS.map((h) => (
            <div key={h} className="text-sm text-muted-foreground">
              · {h}
            </div>
          ))}
        </div>
      </section>

      {/* Three product shapes */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-center text-2xl font-bold">三种产品形态，共享同一套平台能力</h2>
        <p className="mt-2 text-center text-sm text-muted-foreground">
          证券代码、数据集、指标、API、身份与权益统一；页面、运行状态与私有数据分离。
        </p>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {PRODUCTS.map(({ icon: Icon, name, desc, href, cta }) => (
            <div key={name} className="flex flex-col rounded-xl border bg-card p-6 shadow-sm">
              <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-lg font-semibold">{name}</h3>
              <p className="mt-2 flex-1 text-sm text-muted-foreground">{desc}</p>
              <Link
                to={href}
                className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                {cta} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="mx-auto max-w-6xl px-4 pb-20">
        <div className="rounded-2xl border bg-card p-10 text-center shadow-sm">
          <h2 className="text-2xl font-bold">开始使用 SigmX</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            注册即获免费版、50 研究积分和每月 1,000 Data Credit。
          </p>
          <Link
            to="/register"
            className="mt-6 inline-flex h-11 items-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            免费注册
          </Link>
        </div>
      </section>
    </div>
  );
}
