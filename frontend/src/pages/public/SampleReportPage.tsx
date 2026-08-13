/**
 * Sample report page (design §7.1 /reports/sample/:slug): a bundled, sanitized
 * public sample of an AlphaForge-style report. No real ticker/position data —
 * illustrative only. Static content keyed by slug.
 */
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, FileText } from "lucide-react";

interface SampleReport {
  title: string;
  summary: string;
  sections: { heading: string; body: string }[];
}

const SAMPLES: Record<string, SampleReport> = {
  "alphaforge-demo": {
    title: "AlphaForge 研报样例（脱敏）",
    summary:
      "这是一份示例性的多智能体个股研报，所有数据均为虚构，仅用于展示报告结构与产品能力。",
    sections: [
      {
        heading: "公司概况",
        body: "示例公司是一家虚构的A股上市公司，主营业务为示例行业。本节由概况智能体生成，汇总基本面与行业地位。",
      },
      {
        heading: "财务质量",
        body: "财务智能体对营收、利润、现金流与资产负债结构进行质量评估。样例数据不构成任何投资建议。",
      },
      {
        heading: "风险提示",
        body: "本报告为脱敏样例，不针对任何真实证券。投资有风险，决策需谨慎。",
      },
    ],
  },
};

export function SampleReportPage() {
  const { slug } = useParams<{ slug: string }>();
  const report = slug ? SAMPLES[slug] : undefined;

  if (!report) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <FileText className="mx-auto h-10 w-10 text-muted-foreground" />
        <h1 className="mt-4 text-xl font-semibold">未找到该样例报告</h1>
        <p className="mt-2 text-sm text-muted-foreground">slug: {slug ?? "（空）"}</p>
        <Link
          to="/"
          className="mt-6 inline-flex h-10 items-center gap-1 rounded-md border px-4 text-sm hover:bg-muted"
        >
          <ArrowLeft className="h-4 w-4" /> 返回首页
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        to="/"
        className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> 返回首页
      </Link>

      <article>
        <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
          <FileText className="h-3 w-3" /> 脱敏样例 · 非真实研报
        </div>
        <h1 className="text-3xl font-bold tracking-tight">{report.title}</h1>
        <p className="mt-3 text-muted-foreground">{report.summary}</p>

        <div className="mt-8 space-y-8">
          {report.sections.map((s) => (
            <section key={s.heading}>
              <h2 className="text-lg font-semibold">{s.heading}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
            </section>
          ))}
        </div>
      </article>
    </div>
  );
}
