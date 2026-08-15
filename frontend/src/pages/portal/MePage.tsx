import { useCallback, useEffect, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Cloud,
  Coins,
  Database,
  Download,
  Laptop,
  RefreshCw,
  Settings2,
} from "lucide-react";

import {
  getMyCredits,
  getMyEntitlements,
  getMyUsage,
  listDevices,
  type CreditsBalanceResponse,
  type DeviceItem,
  type EntitlementsResponse,
  type UsageResponse,
} from "@/lib/productApi";

interface ProductState {
  entitlements: EntitlementsResponse | null;
  credits: CreditsBalanceResponse | null;
  usage: UsageResponse | null;
  devices: DeviceItem[] | null;
}

const EMPTY_STATE: ProductState = {
  entitlements: null,
  credits: null,
  usage: null,
  devices: null,
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function MePage() {
  const [state, setState] = useState<ProductState>(EMPTY_STATE);
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      getMyEntitlements(),
      getMyCredits(),
      getMyUsage(),
      listDevices(),
    ] as const);

    setState({
      entitlements: results[0].status === "fulfilled" ? results[0].value : null,
      credits: results[1].status === "fulfilled" ? results[1].value : null,
      usage: results[2].status === "fulfilled" ? results[2].value : null,
      devices: results[3].status === "fulfilled" ? results[3].value : null,
    });
    setHasError(results.some((result) => result.status === "rejected"));
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activeDevices = state.devices?.filter((device) => !device.revoked_at).length;
  const deviceLimit = state.entitlements?.entitlements["desktop.device_limit"];

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8">
      <header className="flex flex-col gap-4 border-b pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary">Cloud workspace</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">我的 SigmX</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Web 管理云资产与产品权益；Desktop 作为 Financial Harness 完成深度研究、量化验证和持续监控。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/account"
            className="inline-flex h-9 items-center gap-2 rounded-md border bg-card px-3 text-sm font-medium hover:bg-muted"
          >
            <Settings2 className="h-4 w-4" />
            管理账户
          </Link>
          <Link
            to="/download"
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Download className="h-4 w-4" />
            下载 Desktop
          </Link>
        </div>
      </header>

      {hasError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
          <span>
            <strong className="font-medium">部分产品状态暂时不可用</strong>
            <span className="ml-1 text-muted-foreground">已保留成功加载的内容。</span>
          </span>
          <button type="button" onClick={() => void load()} className="inline-flex items-center gap-1.5 font-medium text-primary">
            <RefreshCw className="h-3.5 w-3.5" />
            重试
          </button>
        </div>
      )}

      <section aria-label="产品状态" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatusCard
          icon={Cloud}
          label="当前套餐"
          value={loading ? "加载中…" : state.entitlements?.plan_code ?? "暂不可用"}
          detail={state.entitlements?.valid_until ? `有效期至 ${state.entitlements.valid_until.slice(0, 10)}` : "由云端权益统一管理"}
        />
        <StatusCard
          icon={Coins}
          label="研究积分"
          value={loading ? "加载中…" : state.credits ? formatNumber(state.credits.available) : "暂不可用"}
          detail={state.credits ? `${formatNumber(state.credits.expiring_soon)} 积分即将到期` : "用于 AI 研究与云任务"}
        />
        <StatusCard
          icon={Database}
          label="Data Hub 今日用量"
          value={loading ? "加载中…" : state.usage ? `${formatNumber(state.usage.consumed)} / ${formatNumber(state.usage.quota_daily)}` : "暂不可用"}
          detail={state.usage ? `剩余 ${formatNumber(state.usage.remaining)}` : "数据用量独立计量"}
          to="/account/usage"
        />
        <StatusCard
          icon={Laptop}
          label="活跃设备"
          value={loading ? "加载中…" : activeDevices === undefined ? "暂不可用" : `${activeDevices} / ${typeof deviceLimit === "number" ? deviceLimit : "—"}`}
          detail="Desktop 通过设备授权连接云账户"
          to="/account/devices"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <AssetCard icon={BarChart3} title="我的自选" description="跨端自选将在研究闭环阶段接入，这里将只展示用户主动同步的云资产。" />
        <AssetCard icon={RefreshCw} title="保存的查询" description="Web 自然语言选股上线后，可在这里继续查看条件变化和历史结果。" />
        <AssetCard icon={Cloud} title="我的报告" description="本地完整报告默认不上云；用户主动生成的云报告或脱敏摘要会显示在这里。" />
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <ProductCard
          title="SigmX Desktop"
          eyebrow="Financial Harness"
          description="连接本地数据、专业工具与多个金融智能体，运行可验证、可复现的完整研究工作流。"
          to="/product/desktop"
          action="了解 Desktop"
        />
        <ProductCard
          title="SigmX Data Hub"
          eyebrow="Financial Data Infrastructure"
          description="为 Desktop、Python 和企业系统提供标准化、带质量状态和用量计量的金融数据。"
          to="/product/data-hub"
          action="了解 Data Hub"
        />
      </section>

      <p className="border-t pt-5 text-xs leading-5 text-muted-foreground">
        SigmX 提供研究与信息工具，不构成投资建议、收益承诺或自动交易指令。
      </p>
    </div>
  );
}

function StatusCard({
  icon: Icon,
  label,
  value,
  detail,
  to,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail: string;
  to?: string;
}) {
  const body = (
    <div className="rounded-md border bg-card p-4 shadow-sm shadow-black/[0.02]">
      <div className="flex items-center justify-between gap-3 text-muted-foreground">
        <span className="text-xs font-medium">{label}</span>
        <Icon className="h-4 w-4" />
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-tight">{value}</div>
      <p className="mt-2 text-xs text-muted-foreground">{detail}</p>
    </div>
  );

  return to ? <Link to={to}>{body}</Link> : body;
}

function AssetCard({ icon: Icon, title, description }: { icon: ComponentType<{ className?: string }>; title: string; description: string }) {
  return (
    <div className="rounded-md border border-dashed bg-muted/10 p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">{title}</h2>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">规划中</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{description}</p>
    </div>
  );
}

function ProductCard({ title, eyebrow, description, to, action }: { title: string; eyebrow: string; description: string; to: string; action: string }) {
  return (
    <Link to={to} className="group rounded-md border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-primary/[0.02]">
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-primary">{eyebrow}</p>
      <h2 className="mt-2 text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
      <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary">
        {action}
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}
