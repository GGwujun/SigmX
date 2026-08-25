import { useEffect, useState } from "react";
import {
  ArrowRight,
  BellRing,
  Check,
  ChevronRight,
  Download,
  LineChart,
  LockKeyhole,
  Monitor,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

const workflow = [
  ["01", "Web 发现机会", "从市场与情报中快速缩小研究范围"],
  ["02", "Desktop 深入验证", "对比公司、验证因子并检查完整证据链"],
  ["03", "建立持续跟踪", "把结论转成定时任务、事件规则和风险提醒"],
  ["04", "自动提醒与复盘", "新公告、价格和指标变化触发研究更新"],
] as const;

const modeContent = {
  standalone: {
    eyebrow: "无需云服务",
    title: "数据、模型和任务都留在本机",
    description:
      "断网也能打开持仓、自选、报告和历史研究。可使用本地数据源、自带模型 Key 或本地模型。",
    points: [
      "私有持仓与交易日志",
      "本地报告、策略与回测",
      "离线定时任务",
      "本地模型与自带 Key",
    ],
  },
  connected: {
    eyebrow: "扩展数据能力",
    title: "连接 Data Hub，获得持续更新的数据",
    description:
      "通过设备授权访问标准化行情、财务和情报数据，在保留本地私有数据的同时扩展云端能力。",
    points: [
      "标准化 Data Hub 数据",
      "实时行情与事件更新",
      "跨设备同步研究配置",
      "统一账号与权益",
    ],
  },
} as const;

const capabilityRows = [
  ["快速发现机会", "支持", "支持", "—"],
  ["本地持仓与私有数据", "—", "核心能力", "—"],
  ["回测与持续任务", "—", "核心能力", "—"],
  ["标准化数据接口", "—", "可连接", "核心能力"],
  ["无需安装", "支持", "—", "支持"],
] as const;

const RELEASE_API =
  "https://api.github.com/repos/GGwujun/SigmX/releases/latest";
const WINDOWS_FALLBACK =
  "https://github.com/GGwujun/SigmX/releases/download/v0.1.7/SigmX-Setup-0.1.7.exe";

type DesktopDownloads = { windows: string; mac?: string; version: string };

function useDesktopDownloads(): DesktopDownloads {
  const [downloads, setDownloads] = useState<DesktopDownloads>({
    windows: WINDOWS_FALLBACK,
    version: "v0.1.7",
  });
  useEffect(() => {
    let cancelled = false;
    void fetch(RELEASE_API, {
      headers: { Accept: "application/vnd.github+json" },
    })
      .then((response) =>
        response.ok
          ? response.json()
          : Promise.reject(new Error("release unavailable")),
      )
      .then(
        (release: {
          tag_name?: string;
          assets?: Array<{ name: string; browser_download_url: string }>;
        }) => {
          if (cancelled) return;
          const assets = release.assets ?? [];
          const windows = assets.find((asset) =>
            asset.name.toLowerCase().endsWith(".exe"),
          );
          const mac = assets.find((asset) =>
            asset.name.toLowerCase().endsWith(".dmg"),
          );
          setDownloads({
            windows: windows?.browser_download_url ?? WINDOWS_FALLBACK,
            mac: mac?.browser_download_url,
            version: release.tag_name ?? "v0.1.7",
          });
        },
      )
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return downloads;
}

export function DesktopProductPage() {
  const [mode, setMode] = useState<keyof typeof modeContent>("standalone");
  const activeMode = modeContent[mode];
  const downloads = useDesktopDownloads();

  return (
    <div className="bg-slate-50 text-slate-950">
      <section className="overflow-hidden border-b border-slate-800 bg-slate-950 text-white">
        <div className="mx-auto grid max-w-[1440px] gap-8 px-4 py-14 md:grid-cols-[0.82fr_1.18fr] lg:px-8 lg:py-20">
          <div className="flex flex-col justify-center">
            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-teal-400/30 bg-teal-400/10 px-3 py-1 text-xs font-semibold text-teal-300">
              <Monitor className="h-3.5 w-3.5" /> SIGMX DESKTOP
            </div>
            <h1 className="mt-5 max-w-xl text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              本地优先的
              <br />
              <span className="text-teal-300">专业投研工作台</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-300">
              把一次性的市场发现，变成可验证、可跟踪、可复盘的长期研究任务。持仓、交易日志和私有文件默认只保存在你的设备。
            </p>
            <div className="mt-6 grid max-w-xl grid-cols-2 gap-3 text-sm text-slate-200">
              <Value icon={LockKeyhole} label="私有数据不出设备" />
              <Value icon={RefreshCw} label="持续运行的研究任务" />
              <Value icon={LineChart} label="回测与因子验证" />
              <Value icon={BellRing} label="事件触发与风险提醒" />
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <DownloadLink
                href={downloads.windows}
                platform="Windows"
                primary
              />
              <DownloadLink href={downloads.mac} platform="Mac" />
              <a
                href="#workflow"
                className="inline-flex h-11 items-center gap-2 rounded-lg border border-slate-700 px-5 text-sm font-semibold text-white hover:bg-slate-900"
              >
                <Play className="h-4 w-4" />
                查看工作流演示
              </a>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Windows 10/11 · {downloads.mac ? "macOS 12+" : "Mac 版正在构建"} · {downloads.version} · 安装包由 GitHub
              Releases 提供
            </p>
          </div>
          <DesktopPreview />
        </div>
      </section>

      <section
        id="workflow"
        className="mx-auto max-w-[1280px] px-4 py-16 lg:px-8"
      >
        <SectionTitle
          eyebrow="从发现到持续研究"
          title="一条完整的投研工作流"
          description="Web 负责快速发现，Desktop 承接深入验证、持续运行与本地私有数据。"
        />
        <div className="mt-9 grid gap-3 lg:grid-cols-4">
          {workflow.map(([number, title, description], index) => (
            <div
              key={title}
              className="relative rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="text-xs font-bold text-teal-600">{number}</div>
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {description}
              </p>
              {index < workflow.length - 1 && (
                <ChevronRight className="absolute -right-4 top-1/2 z-10 hidden h-5 w-5 -translate-y-1/2 rounded-full bg-slate-50 text-slate-400 lg:block" />
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="border-y border-slate-200 bg-white">
        <div className="mx-auto grid max-w-[1280px] gap-10 px-4 py-16 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
          <div>
            <SectionTitle
              eyebrow="两种运行方式"
              title="本地独立，也能连接云端"
              description="你决定哪些能力留在本机，什么时候使用 Data Hub。"
            />
            <div className="mt-7 grid grid-cols-2 rounded-lg bg-slate-100 p-1">
              <button
                type="button"
                aria-pressed={mode === "standalone"}
                onClick={() => setMode("standalone")}
                className={`rounded-md px-4 py-2.5 text-sm font-semibold ${mode === "standalone" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
              >
                Standalone
              </button>
              <button
                type="button"
                aria-pressed={mode === "connected"}
                onClick={() => setMode("connected")}
                className={`rounded-md px-4 py-2.5 text-sm font-semibold ${mode === "connected" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
              >
                Connected
              </button>
            </div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-7">
            <div className="text-xs font-bold uppercase tracking-wider text-teal-600">
              {activeMode.eyebrow}
            </div>
            <h3 className="mt-2 text-2xl font-bold">{activeMode.title}</h3>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              {activeMode.description}
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {activeMode.points.map((point) => (
                <div
                  key={point}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm font-medium"
                >
                  <Check className="h-4 w-4 text-teal-600" />
                  {point}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1100px] px-4 py-16 lg:px-8">
        <SectionTitle
          eyebrow="产品边界"
          title="不是 Web 的复制，而是长期研究的主场"
          description="三个产品共享账号、数据定义和研究资产，但承担不同任务。"
          align="center"
        />
        <div className="mt-9 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table aria-label="产品能力边界" className="w-full text-left text-sm">
            <thead className="bg-slate-950 text-white">
              <tr>
                <th className="px-5 py-4 font-semibold">能力</th>
                <th className="px-5 py-4 font-semibold">Web</th>
                <th className="px-5 py-4 font-semibold text-teal-300">
                  Desktop
                </th>
                <th className="px-5 py-4 font-semibold">Data Hub</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {capabilityRows.map((row) => (
                <tr key={row[0]}>
                  <td className="px-5 py-4 font-medium">{row[0]}</td>
                  {row.slice(1).map((value, index) => (
                    <td
                      key={`${row[0]}-${index}`}
                      className={`px-5 py-4 ${index === 1 ? "bg-teal-50/50 font-semibold text-teal-700" : "text-slate-500"}`}
                    >
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-slate-800 bg-slate-950 text-white">
        <div className="mx-auto flex max-w-[1100px] flex-col items-center justify-between gap-6 px-4 py-12 text-center md:flex-row md:text-left lg:px-8">
          <div>
            <div className="text-xs font-bold text-teal-300">SIGMX DESKTOP</div>
            <h2 className="mt-2 text-2xl font-bold">
              设备保持运行，研究任务就能持续执行
            </h2>
            <p className="mt-2 text-sm text-slate-400">
              任务在你的设备本地运行；休眠或关机时会暂停，恢复后继续。需要时可连接
              Data Hub。
            </p>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            <DownloadLink
              href={downloads.windows}
              platform="Windows"
              primary
              arrow
            />
            <DownloadLink href={downloads.mac} platform="Mac" arrow />
          </div>
        </div>
      </section>
    </div>
  );
}

function DownloadLink({
  href,
  platform,
  primary = false,
  arrow = false,
}: {
  href?: string;
  platform: "Windows" | "Mac";
  primary?: boolean;
  arrow?: boolean;
}) {
  const className = `inline-flex h-11 shrink-0 items-center gap-2 rounded-lg px-5 text-sm font-bold ${primary ? "bg-teal-400 text-slate-950 hover:bg-teal-300" : "border border-slate-700 text-white hover:bg-slate-900"}`;
  if (!href)
    return (
      <span
        aria-label={`下载 Mac 版（等待 Release 构建）`}
        aria-disabled="true"
        className={`${className} cursor-not-allowed opacity-50`}
      >
        <Download className="h-4 w-4" />
        下载 Mac 版 · 构建中
      </span>
    );
  return (
    <a href={href} className={className}>
      <Download className="h-4 w-4" />
      下载 {platform} 版 {arrow && <ArrowRight className="h-4 w-4" />}
    </a>
  );
}

function DesktopPreview() {
  return (
    <div className="self-center overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
      <div className="flex h-9 items-center justify-between border-b border-slate-700 px-4 text-[10px] text-slate-500">
        <span>SigmX Desktop · 研究工作台</span>
        <span className="inline-flex items-center gap-1 text-teal-300">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-400" />
          本地运行中
        </span>
      </div>
      <div className="grid min-h-[390px] grid-cols-[145px_minmax(0,1fr)] sm:grid-cols-[170px_minmax(0,1fr)]">
        <aside className="border-r border-slate-800 p-3">
          <div className="flex items-center gap-2 rounded-md bg-slate-800 px-2 py-2 text-xs text-slate-300">
            <Search className="h-3.5 w-3.5" />
            搜索研究资产
          </div>
          <div className="mt-4 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            今日任务
          </div>
          {["早盘市场扫描", "持仓风险检查", "AI 算力产业链"].map(
            (item, index) => (
              <div
                key={item}
                className={`mt-2 rounded-md px-2 py-2 text-xs ${index === 2 ? "bg-teal-400/10 text-teal-300" : "text-slate-400"}`}
              >
                {item}
              </div>
            ),
          )}
          <div className="mt-5 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
            本地资产
          </div>
          {["我的持仓", "自选列表", "历史报告"].map((item) => (
            <div key={item} className="mt-2 px-2 text-xs text-slate-400">
              {item}
            </div>
          ))}
        </aside>
        <div className="min-w-0 p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs text-teal-300">持续研究任务</div>
              <div className="mt-1 text-sm font-semibold">
                国产算力产业链跟踪
              </div>
            </div>
            <span className="rounded bg-teal-400/10 px-2 py-1 text-[10px] text-teal-300">
              运行中
            </span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {[
              ["候选", "18"],
              ["新证据", "7"],
              ["风险提醒", "2"],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-slate-800 bg-slate-950 p-3"
              >
                <div className="text-[10px] text-slate-500">{label}</div>
                <div className="mt-1 text-lg font-semibold text-slate-100">
                  {value}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">Agent 执行过程</span>
              <Sparkles className="h-3.5 w-3.5 text-teal-300" />
            </div>
            {[
              "同步最新公告与行业数据",
              "更新 18 家候选公司的盈利预测",
              "检查持仓暴露与事件风险",
            ].map((item, index) => (
              <div
                key={item}
                className="mt-3 flex items-center gap-2 text-[11px] text-slate-400"
              >
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded-full ${index < 2 ? "bg-teal-400/15 text-teal-300" : "bg-slate-800 text-slate-500"}`}
                >
                  {index < 2 ? "✓" : "3"}
                </span>
                {item}
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
            <div>
              <div className="text-[10px] font-semibold text-amber-300">
                新风险事件
              </div>
              <div className="mt-1 text-xs text-slate-300">
                海外管制政策可能影响上游设备交付
              </div>
            </div>
            <BellRing className="h-4 w-4 text-amber-300" />
          </div>
        </div>
      </div>
    </div>
  );
}

function Value({
  icon: Icon,
  label,
}: {
  icon: typeof ShieldCheck;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-900">
        <Icon className="h-4 w-4 text-teal-300" />
      </span>
      {label}
    </div>
  );
}
function SectionTitle({
  eyebrow,
  title,
  description,
  align = "left",
}: {
  eyebrow: string;
  title: string;
  description: string;
  align?: "left" | "center";
}) {
  return (
    <div className={align === "center" ? "text-center" : ""}>
      <div className="text-xs font-bold uppercase tracking-wider text-teal-600">
        {eyebrow}
      </div>
      <h2 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">
        {title}
      </h2>
      <p
        className={`mt-3 text-sm leading-6 text-slate-500 ${align === "center" ? "mx-auto max-w-2xl" : "max-w-xl"}`}
      >
        {description}
      </p>
    </div>
  );
}
