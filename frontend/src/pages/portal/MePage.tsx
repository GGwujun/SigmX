import { useCallback, useEffect, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  Bell,
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
  getDataCreditBalance,
  getDataHubUsage,
  getMyEntitlements,
  listDevices,
  listNotifications,
  markNotificationRead,
  getNotificationPreferences,
  putNotificationPreferences,
  listSavedQuerySubscriptions,
  putSavedQuerySubscription,
  deleteSavedQuerySubscription,
  type CreditsBalanceResponse,
  type DataCreditBalance,
  type DataHubUsage,
  type DeviceItem,
  type EntitlementsResponse,
  type NotificationPreferences,
  type PersonalNotification,
  type SavedQuerySubscription,
} from "@/lib/productApi";
import { cloudResearchApi, type CloudReport, type CloudSavedQuery, type CloudWatchlistItem } from "@/lib/cloudResearchApi";

interface ProductState {
  entitlements: EntitlementsResponse | null;
  credits: CreditsBalanceResponse | null;
  dataCredits: DataCreditBalance | null;
  usage: DataHubUsage | null;
  devices: DeviceItem[] | null;
  queries: CloudSavedQuery[] | null;
  watchlist: CloudWatchlistItem[] | null;
  reports: CloudReport[] | null;
  notifications: PersonalNotification[] | null;
  notificationPreferences: NotificationPreferences | null;
  querySubscriptions: SavedQuerySubscription[] | null;
}

const EMPTY_STATE: ProductState = {
  entitlements: null,
  credits: null,
  dataCredits: null,
  usage: null,
  devices: null,
  queries: null,
  watchlist: null,
  reports: null,
  notifications: null,
  notificationPreferences: null,
  querySubscriptions: null,
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function MePage() {
  const [state, setState] = useState<ProductState>(EMPTY_STATE);
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [desktopLink, setDesktopLink] = useState<string | null>(null);
  const [handoffError, setHandoffError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      getMyEntitlements(),
      getMyCredits(),
      getDataCreditBalance(),
      getDataHubUsage(),
      listDevices(),
      cloudResearchApi.listQueries(),
      cloudResearchApi.listWatchlist(),
      cloudResearchApi.listReports(),
      listNotifications(),
      getNotificationPreferences(),
      listSavedQuerySubscriptions(),
    ] as const);

    setState({
      entitlements: results[0].status === "fulfilled" ? results[0].value : null,
      credits: results[1].status === "fulfilled" ? results[1].value : null,
      dataCredits: results[2].status === "fulfilled" ? results[2].value : null,
      usage: results[3].status === "fulfilled" ? results[3].value : null,
      devices: results[4].status === "fulfilled" ? results[4].value : null,
      queries: results[5].status === "fulfilled" ? results[5].value : null,
      watchlist: results[6].status === "fulfilled" ? results[6].value : null,
      reports: results[7].status === "fulfilled" ? results[7].value : null,
      notifications: results[8].status === "fulfilled" ? results[8].value : null,
      notificationPreferences: results[9].status === "fulfilled" ? results[9].value : null,
      querySubscriptions: results[10].status === "fulfilled" ? results[10].value : null,
    });
    setHasError(results.some((result) => result.status === "rejected"));
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const activeDevices = state.devices?.filter((device) => !device.revoked_at).length;
  const deviceLimit = state.entitlements?.entitlements["desktop.device_limit"];

  const createHandoff = async (kind: "saved_query" | "instrument", payload: Record<string, string>) => {
    setHandoffError(null);
    try {
      setDesktopLink((await cloudResearchApi.createHandoff(kind, payload)).deep_link);
    } catch (error) {
      setHandoffError(error instanceof Error ? error.message : "暂时无法创建 Desktop 任务");
    }
  };

  const readNotification = async (id: string) => {
    await markNotificationRead(id);
    setState((current) => ({
      ...current,
      notifications: current.notifications?.map((item) =>
        item.id === id ? { ...item, read_at: new Date().toISOString() } : item
      ) ?? null,
    }));
  };

  const changePreference = async (key: keyof NotificationPreferences, value: boolean) => {
    if (!state.notificationPreferences) return;
    const next = { ...state.notificationPreferences, [key]: value };
    setState((current) => ({ ...current, notificationPreferences: next }));
    try {
      const saved = await putNotificationPreferences(next);
      setState((current) => ({ ...current, notificationPreferences: saved }));
    } catch {
      setHasError(true);
    }
  };

  const changeQuerySubscription = async (savedQueryId: string, frequency: "off" | "daily" | "weekly") => {
    try {
      const existing = state.querySubscriptions?.find((item) => item.saved_query_id === savedQueryId);
      if (frequency === "off") {
        if (existing) await deleteSavedQuerySubscription(existing.id);
        setState((current) => ({
          ...current,
          querySubscriptions: current.querySubscriptions?.filter((item) => item.saved_query_id !== savedQueryId) ?? null,
        }));
        return;
      }
      const saved = await putSavedQuerySubscription(savedQueryId, frequency);
      setState((current) => ({
        ...current,
        querySubscriptions: [
          ...(current.querySubscriptions ?? []).filter((item) => item.saved_query_id !== savedQueryId),
          saved,
        ],
      }));
    } catch {
      setHasError(true);
    }
  };

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
          label="Data Credit"
          value={loading ? "加载中…" : state.dataCredits ? formatNumber(state.dataCredits.available) : "暂不可用"}
          detail={state.usage ? `${formatNumber(state.usage.total_requests)} 次调用，已扣 ${formatNumber(state.usage.credits_charged)}` : "数据积分独立计量"}
          to="/account/data-hub"
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
        <AssetList icon={BarChart3} title="我的自选" empty="尚未同步云自选。" items={(state.watchlist ?? []).map((item) => ({ key: item.symbol, title: item.name || item.symbol, detail: item.symbol, to: `/stock/${item.symbol}`, handoff: () => createHandoff("instrument", { symbol: item.symbol }) }))} unavailable={state.watchlist === null && !loading} />
        <AssetList icon={RefreshCw} title="保存的查询" empty="尚未保存 Web 查询。" items={(state.queries ?? []).map((item) => ({ key: item.id, title: item.query, detail: `${String(item.result_summary.matches ?? 0)} 个结果`, to: `/query/${encodeURIComponent(item.query)}`, handoff: () => createHandoff("saved_query", { query: item.query, saved_query_id: item.id }) }))} unavailable={state.queries === null && !loading} />
        <AssetList icon={Cloud} title="我的报告" empty="尚未发布脱敏报告快照。" items={(state.reports ?? []).filter((item) => !item.revoked_at).map((item) => ({ key: item.id, title: item.title, detail: "打开公开快照", to: `/research/${item.slug}` }))} unavailable={state.reports === null && !loading} />
      </section>

      {(state.queries?.length ?? 0) > 0 && <section className="rounded-md border bg-card p-4">
        <div className="flex items-center gap-2"><RefreshCw className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">查询复查订阅</h2></div>
        <p className="mt-1 text-xs text-muted-foreground">按日或按周提醒你复查保存的云端查询；结果仍由你决定是否交给 Desktop 深入研究。</p>
        <div className="mt-3 divide-y">
          {(state.queries ?? []).map((query) => {
            const subscription = state.querySubscriptions?.find((item) => item.saved_query_id === query.id);
            return <div key={query.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div><p className="text-sm font-medium">{query.query}</p>{subscription && <p className="mt-1 text-xs text-muted-foreground">下次提醒：{subscription.next_run_at.slice(0, 10)}</p>}</div>
              <select aria-label={`复查频率：${query.query}`} value={subscription?.frequency ?? "off"} onChange={(event) => void changeQuerySubscription(query.id, event.target.value as "off" | "daily" | "weekly")} className="h-9 rounded-md border bg-background px-3 text-sm">
                <option value="off">不订阅</option><option value="daily">每天</option><option value="weekly">每周</option>
              </select>
            </div>;
          })}
        </div>
      </section>}

      <section className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-md border bg-card p-4">
          <div className="flex items-center gap-2"><Bell className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">通知</h2></div>
          <div className="mt-3 space-y-2">
            {state.notifications?.length === 0 && <p className="text-xs text-muted-foreground">暂无通知。</p>}
            {(state.notifications ?? []).slice(0, 10).map((item) => <button key={item.id} type="button" onClick={() => void readNotification(item.id)} className="block w-full rounded-md border px-3 py-2 text-left"><div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{item.title}</span>{!item.read_at && <span className="h-2 w-2 rounded-full bg-primary" aria-label="未读" />}</div><p className="mt-1 text-xs text-muted-foreground">{item.body}</p></button>)}
          </div>
        </div>
        <div className="rounded-md border bg-card p-4">
          <h2 className="text-sm font-semibold">通知偏好</h2>
          <div className="mt-3 space-y-3 text-sm">
            {state.notificationPreferences && ([
              ["budget_alerts", "Data Hub 预算告警"],
              ["product_updates", "套餐与积分到账"],
              ["cloud_tasks", "云任务状态"],
            ] as const).map(([key, label]) => <label key={key} className="flex items-center justify-between gap-3"><span>{label}</span><input aria-label={label} type="checkbox" checked={state.notificationPreferences?.[key] ?? false} onChange={(event) => void changePreference(key, event.target.checked)} /></label>)}
          </div>
        </div>
      </section>

      {(desktopLink || handoffError) && <section className="rounded-md border border-primary/25 bg-primary/5 p-4 text-sm">
        {handoffError ? <p className="text-destructive">{handoffError}</p> : <div className="flex flex-wrap items-center gap-3"><span>一次性研究任务已就绪，10 分钟内有效。</span><a href={desktopLink!} className="font-medium text-primary">打开 Desktop</a><Link to="/download" className="text-xs text-muted-foreground underline">尚未安装？下载 Desktop</Link></div>}
      </section>}

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
          description="为 Desktop 和个人开发者提供标准化、带质量状态和用量计量的金融数据。"
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

function AssetList({ icon: Icon, title, items, empty, unavailable }: { icon: ComponentType<{ className?: string }>; title: string; items: Array<{ key: string; title: string; detail: string; to: string; handoff?: () => void }>; empty: string; unavailable: boolean }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">{title}</h2>
      </div>
      <div className="mt-3 space-y-2">
        {unavailable && <p className="text-xs text-muted-foreground">暂时无法加载。</p>}
        {!unavailable && items.length === 0 && <p className="text-xs text-muted-foreground">{empty}</p>}
        {items.slice(0, 5).map((item) => <div key={item.key} className="rounded-md border px-3 py-2 hover:border-primary/40"><Link to={item.to} className="block"><div className="truncate text-sm font-medium">{item.title}</div><div className="mt-1 text-xs text-muted-foreground">{item.detail}</div></Link>{item.handoff && <button type="button" aria-label={`在 Desktop 继续：${item.title}`} onClick={item.handoff} className="mt-2 text-xs font-medium text-primary">在 Desktop 继续 →</button>}</div>)}
      </div>
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
