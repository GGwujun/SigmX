import { useCallback, useEffect, useState } from "react";
import { Copy, Database, KeyRound, RefreshCw, RotateCw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { AccountPage } from "@/components/layout/AccountPage";
import {
  createDataHubCredential,
  getDataCreditBalance,
  getDataCreditLedger,
  getDataCreditLots,
  getDataCreditPacks,
  getDataHubUsage,
  getDataHubLogs,
  getDataHubBudgetAlerts,
  setDataHubBudget,
  getDataHubBudgets,
  listDataHubCredentials,
  revokeDataHubCredential,
  rotateDataHubCredential,
  redeemDataCreditPack,
  type CreatedDataHubCredential,
  type DataCreditBalance,
  type DataCreditLedgerEntry,
  type DataCreditLot,
  type DataCreditPack,
  type DataHubCredential,
  type DataHubUsage,
  type DataHubRequestLog,
  type DataHubBudgetAlert,
  type DataHubBudget,
} from "@/lib/productApi";

export function DataHubConsolePage() {
  const [balance, setBalance] = useState<DataCreditBalance | null>(null);
  const [usage, setUsage] = useState<DataHubUsage | null>(null);
  const [lots, setLots] = useState<DataCreditLot[]>([]);
  const [ledger, setLedger] = useState<DataCreditLedgerEntry[]>([]);
  const [credentials, setCredentials] = useState<DataHubCredential[]>([]);
  const [name, setName] = useState("");
  const [scopeText, setScopeText] = useState("");
  const [ipText, setIpText] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [secret, setSecret] = useState<CreatedDataHubCredential | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState<DataHubRequestLog[]>([]);
  const [alerts, setAlerts] = useState<DataHubBudgetAlert[]>([]);
  const [budgetInputs, setBudgetInputs] = useState<Record<string, string>>({});
  const [budgets, setBudgets] = useState<Record<string, DataHubBudget>>({});
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [packs, setPacks] = useState<DataCreditPack[]>([]);
  const [packCode, setPackCode] = useState("");
  const [redeemingPack, setRedeemingPack] = useState(false);

  const reload = useCallback(async () => {
    setError("");
    try {
      const [nextBalance, nextUsage, nextCredentials, nextLots, nextLedger, nextLogs, nextAlerts, nextBudgets, nextPacks] = await Promise.all([
        getDataCreditBalance(), getDataHubUsage(), listDataHubCredentials(), getDataCreditLots(), getDataCreditLedger(), getDataHubLogs(false), getDataHubBudgetAlerts(), getDataHubBudgets(), getDataCreditPacks(),
      ]);
      setBalance(nextBalance);
      setUsage(nextUsage);
      setCredentials(nextCredentials);
      setLots(nextLots);
      setLedger(nextLedger);
      setLogs(nextLogs);
      setAlerts(nextAlerts);
      setBudgets(Object.fromEntries(nextBudgets.map((item) => [item.credential_id, item])));
      setBudgetInputs(Object.fromEntries(nextBudgets.map((item) => [item.credential_id, String(item.daily_limit)])));
      setPacks(nextPacks);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载 Data Hub 控制台失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    return () => setSecret(null);
  }, [reload]);

  const create = async () => {
    const scopes = scopeText.split(",").map((value) => value.trim()).filter(Boolean);
    if (!name.trim() || scopes.length === 0) {
      setError("请输入 Key 名称和至少一个 Scope");
      return;
    }
    try {
      const created = await createDataHubCredential({
        name: name.trim(),
        scopes,
        ip_allowlist: ipText.split(/[\n,]/).map((value) => value.trim()).filter(Boolean),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
      });
      setSecret(created);
      setName("");
      setScopeText("");
      setIpText("");
      setExpiresAt("");
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建 Key 失败");
    }
  };

  const rotate = async (item: DataHubCredential) => {
    if (!window.confirm(`轮换 ${item.name}？旧 Key 将立即失效。`)) return;
    try {
      setSecret(await rotateDataHubCredential(item.id));
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "轮换 Key 失败");
    }
  };

  const revoke = async (item: DataHubCredential) => {
    if (!window.confirm(`吊销 ${item.name}？此操作立即生效。`)) return;
    try {
      await revokeDataHubCredential(item.id);
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "吊销 Key 失败");
    }
  };

  const saveBudget = async (item: DataHubCredential) => {
    const value = budgetInputs[item.id]?.trim() || "";
    const dailyLimit = value ? Number(value) : null;
    if (dailyLimit !== null && (!Number.isInteger(dailyLimit) || dailyLimit < 1)) {
      setError("每日预算必须是正整数，留空表示不限制"); return;
    }
    try {
      const saved = await setDataHubBudget(item.id, dailyLimit);
      setBudgets((current) => { const next = { ...current }; if (saved) next[item.id] = saved; else delete next[item.id]; return next; });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存预算失败"); }
  };

  const filterLogs = async (onlyErrors: boolean) => {
    setErrorsOnly(onlyErrors);
    try { setLogs(await getDataHubLogs(onlyErrors)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "加载日志失败"); }
  };

  const redeemPack = async () => {
    const code = packCode.trim();
    if (!code || redeemingPack) return;
    setRedeemingPack(true); setError("");
    try {
      await redeemDataCreditPack(code, `data-pack:${code}`);
      setPackCode("");
      await reload();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "兑换数据积分包失败"); }
    finally { setRedeemingPack(false); }
  };

  return (
    <AccountPage>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold"><Database className="h-5 w-5 text-primary" />Data Hub</h1>
          <p className="text-sm text-muted-foreground">个人数据凭证、接口权限与 Data Credit 用量</p>
        </div>
        <div className="flex items-center gap-2"><Link to="/docs/data-hub/" className="rounded-lg border px-3 py-2 text-sm font-medium hover:bg-muted">接口文档与在线调试</Link><button aria-label="刷新" className="rounded-lg border p-2" onClick={() => void reload()}><RefreshCw className="h-4 w-4" /></button></div>
      </header>

      {error && <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
      {loading ? <p className="text-sm text-muted-foreground">加载中…</p> : (
        <section className="grid gap-4 sm:grid-cols-3">
          <Metric label="可用 Data Credit" value={(balance?.available ?? 0).toLocaleString()} />
          <Metric label="7 日内到期" value={(balance?.expiring_soon ?? 0).toLocaleString()} />
          <Metric label="调用与消耗" value={`${usage?.total_requests ?? 0} 次`} detail={`本期已扣 ${usage?.credits_charged ?? 0} Data Credit`} />
        </section>
      )}

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">Data Credit 积分包</h2>
        <p className="mt-1 text-xs text-muted-foreground">积分包独立于套餐，兑换后有效期 12 个月。</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {packs.map((pack) => <div key={pack.code} className="rounded-lg border p-3"><strong>{pack.name_zh}</strong><div className="mt-1 text-lg font-bold">{pack.credits.toLocaleString()}</div><div className="text-xs text-muted-foreground">¥{(pack.price_cny_fen / 100).toFixed(2)} · {pack.valid_days} 天</div></div>)}
        </div>
        <div className="mt-4 flex gap-2">
          <input aria-label="Data Credit 积分包激活码" value={packCode} onChange={(event) => setPackCode(event.target.value)} placeholder="输入已购买的积分包激活码" className="flex-1 rounded-md border bg-background px-3 py-2 text-sm" />
          <button onClick={() => void redeemPack()} disabled={!packCode.trim() || redeemingPack} className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50">{redeemingPack ? "兑换中…" : "兑换积分包"}</button>
        </div>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="flex items-center gap-2 font-semibold"><KeyRound className="h-4 w-4" />创建 Credential</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm">Key 名称<input aria-label="Key 名称" value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2" /></label>
          <label className="text-sm">Scope<input aria-label="Scope" value={scopeText} onChange={(event) => setScopeText(event.target.value)} placeholder="health, group:market.v1" className="mt-1 w-full rounded-md border bg-background px-3 py-2" /></label>
          <label className="text-sm">IP 白名单（可选）<input aria-label="IP 白名单" value={ipText} onChange={(event) => setIpText(event.target.value)} placeholder="203.0.113.8, 198.51.100.0/24" className="mt-1 w-full rounded-md border bg-background px-3 py-2" /></label>
          <label className="text-sm">到期时间（可选）<input aria-label="到期时间" type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} className="mt-1 w-full rounded-md border bg-background px-3 py-2" /></label>
        </div>
        <button onClick={() => void create()} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">创建 Key</button>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">积分批次与账本</h2>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Data Credit 批次</h3>
            {lots.length === 0 && <p className="text-sm text-muted-foreground">暂无积分批次。</p>}
            {lots.slice(0, 10).map((lot) => <div key={lot.id} className="rounded border p-3 text-sm"><div>剩余 {lot.amount_remaining.toLocaleString()} / {lot.amount_total.toLocaleString()}</div><div className="text-xs text-muted-foreground">{lot.source} · {lot.expires_at ? `到期 ${new Date(lot.expires_at).toLocaleString()}` : "永久有效"}</div></div>)}
          </div>
          <div className="space-y-2">
            <h3 className="text-sm font-medium">最近变动</h3>
            {ledger.length === 0 && <p className="text-sm text-muted-foreground">暂无账本记录。</p>}
            {ledger.slice(0, 10).map((entry) => <div key={entry.id} className="flex items-center justify-between rounded border p-3 text-sm"><div><div>{entry.operation}</div><div className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</div></div><strong className={entry.delta < 0 ? "text-destructive" : "text-emerald-600"}>{entry.delta > 0 ? "+" : ""}{entry.delta.toLocaleString()}</strong></div>)}
          </div>
        </div>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">我的 Credential</h2>
        <div className="mt-3 space-y-2">
          {credentials.length === 0 && <p className="text-sm text-muted-foreground">尚未创建 Key。</p>}
          {credentials.map((item) => (
            <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm">
              <div className="min-w-64"><div className="font-medium">{item.name}</div><code className="text-xs text-muted-foreground">{item.key_prefix}…</code><div className="text-xs text-muted-foreground">{item.scopes.join(", ")}</div><div className="mt-2 flex items-end gap-2"><label className="text-xs">每日 Data Credit 预算<input aria-label={`${item.name}每日预算`} type="number" min="1" value={budgetInputs[item.id] ?? ""} onChange={(event) => setBudgetInputs((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="留空不限制" className="mt-1 block w-40 rounded border bg-background px-2 py-1" /></label><button aria-label={`保存${item.name}预算`} onClick={() => void saveBudget(item)} className="rounded border px-2 py-1 text-xs">保存</button></div>{budgets[item.id] && <div className="mt-1 text-xs text-muted-foreground">今日 {budgets[item.id].spent_today}/{budgets[item.id].daily_limit}，剩余 {budgets[item.id].remaining_today}</div>}</div>
              <div className="flex gap-2">
                {!item.revoked_at && <button aria-label={`轮换 ${item.name}`} onClick={() => void rotate(item)} className="rounded border p-2"><RotateCw className="h-4 w-4" /></button>}
                {!item.revoked_at && <button aria-label={`吊销 ${item.name}`} onClick={() => void revoke(item)} className="rounded border p-2 text-destructive"><Trash2 className="h-4 w-4" /></button>}
                {item.revoked_at && <span className="text-xs text-muted-foreground">已吊销</span>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <h2 className="font-semibold">预算告警</h2>
        <div className="mt-3 space-y-2">{alerts.length === 0 ? <p className="text-sm text-muted-foreground">暂无阈值告警。</p> : alerts.slice(0, 20).map((item) => <div key={`${item.credential_id}-${item.utc_date}-${item.threshold_percent}`} className="rounded border border-warning/30 bg-warning/5 p-3 text-sm"><strong>{item.credential_name} · {item.threshold_percent}%</strong><div className="text-xs text-muted-foreground">UTC {item.utc_date} 已使用 {item.spent}/{item.daily_limit} Data Credit</div></div>)}</div>
      </section>

      <section className="rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between"><h2 className="font-semibold">请求与错误日志</h2><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={errorsOnly} onChange={(event) => void filterLogs(event.target.checked)} />仅看错误</label></div>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b"><th className="py-2">时间</th><th>Credential</th><th>接口</th><th>状态</th><th>耗时</th><th>扣分</th><th>错误</th></tr></thead><tbody>{logs.map((item) => <tr key={item.request_id} className="border-b"><td className="py-2">{new Date(item.created_at).toLocaleString()}</td><td>{item.credential_name}</td><td><code>{item.endpoint_code}</code></td><td>{item.status_code}</td><td>{item.duration_ms}ms</td><td>{item.credits_charged}</td><td className="text-destructive">{item.error_code || "—"}</td></tr>)}</tbody></table>{logs.length === 0 && <p className="py-4 text-sm text-muted-foreground">暂无请求日志。</p>}</div>
      </section>

      {secret && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
          <div className="w-full max-w-xl rounded-xl bg-background p-6 shadow-xl">
            <h2 className="font-semibold">保存你的 Data Hub Key</h2>
            <p className="mt-2 text-sm text-amber-600">该密钥仅显示一次，关闭后无法再次查看。</p>
            <div className="mt-4 flex items-center gap-2 rounded-lg border bg-muted p-3"><code className="min-w-0 flex-1 break-all">{secret.plaintext}</code><button aria-label="复制 Key" onClick={() => void navigator.clipboard?.writeText(secret.plaintext)}><Copy className="h-4 w-4" /></button></div>
            <div className="mt-5 flex flex-wrap gap-2"><button className="rounded-md bg-primary px-4 py-2 text-primary-foreground" onClick={() => setSecret(null)}>我已保存</button><Link to="/docs/data-hub/" onClick={() => setSecret(null)} className="rounded-md border px-4 py-2 text-sm">前往接口文档调试</Link></div>
          </div>
        </div>
      )}
    </AccountPage>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="rounded-xl border bg-card p-5"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div>{detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}</div>;
}
