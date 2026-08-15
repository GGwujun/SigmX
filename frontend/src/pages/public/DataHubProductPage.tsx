/**
 * Data Hub product-boundary page (design §7.1 /product/data-hub, §2.2).
 * Explains what Data Hub owns (public data + read-only API + quotas) and what
 * it deliberately does not (private holdings/watchlists). Static content.
 */
import { Link } from "react-router-dom";
import { ArrowRight, Check, Database, X } from "lucide-react";

const OWNS = [
  "行情、财务、新闻、公告、事件、行业与概念数据",
  "公共指标、市场宽度、资金流、热门池与公共推荐",
  "数据采集、标准化、去重、质量校验与新鲜度",
  "只读 API、基于权益的访问、每日配额与用量记录",
];

const DOES_NOT = [
  "用户持仓、自选股与会话",
  "私人报告、订单或模型配置",
  "交易授权；Data Hub API Key 不能访问上述私有数据",
];

export function DataHubProductPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-16">
      <div className="mb-8 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
        <Database className="h-6 w-6 text-primary" />
      </div>
      <h1 className="text-3xl font-bold tracking-tight">Data Hub</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        公共金融数据的权威来源与只读 API。Data Hub 只负责公共数据及其公共计算结果，
        网站与 Connected 客户端只读访问，按套餐配额计量。
      </p>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border bg-card p-6">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-600">
            <Check className="h-4 w-4" /> Data Hub 负责
          </h2>
          <ul className="space-y-2 text-sm">
            {OWNS.map((o) => (
              <li key={o} className="flex gap-2">
                <span className="text-emerald-600">·</span>
                {o}
              </li>
            ))}
          </ul>
        </section>
        <section className="rounded-xl border bg-card p-6">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <X className="h-4 w-4" /> Data Hub 不负责
          </h2>
          <ul className="space-y-2 text-sm text-muted-foreground">
            {DOES_NOT.map((d) => (
              <li key={d} className="flex gap-2">
                <span>·</span>
                {d}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="mt-10 rounded-2xl border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">
          套餐决定可用接口组、速率、并发和每月 Data Credit；每次成功调用按接口成本扣减积分。
        </p>
        <Link
          to="/pricing"
          className="mt-4 inline-flex h-10 items-center gap-1 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          查看套餐 <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}
