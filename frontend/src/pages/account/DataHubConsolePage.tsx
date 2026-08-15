import { useCallback, useEffect, useState } from "react";
import { Copy, Database, KeyRound, RefreshCw, RotateCw, Trash2 } from "lucide-react";

import { AccountNav } from "@/components/layout/AccountNav";
import {
  createDataHubCredential,
  getDataCreditBalance,
  getDataCreditLedger,
  getDataCreditLots,
  getDataHubCatalog,
  getDataHubUsage,
  listDataHubCredentials,
  revokeDataHubCredential,
  rotateDataHubCredential,
  type CreatedDataHubCredential,
  type DataCreditBalance,
  type DataCreditLedgerEntry,
  type DataCreditLot,
  type DataHubCredential,
  type DataHubEndpoint,
  type DataHubUsage,
} from "@/lib/productApi";

export function DataHubConsolePage() {
  const [balance, setBalance] = useState<DataCreditBalance | null>(null);
  const [usage, setUsage] = useState<DataHubUsage | null>(null);
  const [lots, setLots] = useState<DataCreditLot[]>([]);
  const [ledger, setLedger] = useState<DataCreditLedgerEntry[]>([]);
  const [credentials, setCredentials] = useState<DataHubCredential[]>([]);
  const [catalog, setCatalog] = useState<DataHubEndpoint[]>([]);
  const [name, setName] = useState("");
  const [scopeText, setScopeText] = useState("");
  const [ipText, setIpText] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [secret, setSecret] = useState<CreatedDataHubCredential | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setError("");
    try {
      const [nextBalance, nextUsage, nextCredentials, nextCatalog, nextLots, nextLedger] = await Promise.all([
        getDataCreditBalance(), getDataHubUsage(), listDataHubCredentials(), getDataHubCatalog(), getDataCreditLots(), getDataCreditLedger(),
      ]);
      setBalance(nextBalance);
      setUsage(nextUsage);
      setCredentials(nextCredentials);
      setCatalog(nextCatalog);
      setLots(nextLots);
      setLedger(nextLedger);
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

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <AccountNav />
      <header className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold"><Database className="h-5 w-5 text-primary" />Data Hub</h1>
          <p className="text-sm text-muted-foreground">个人数据凭证、接口权限与 Data Credit 用量</p>
        </div>
        <button aria-label="刷新" className="rounded-lg border p-2" onClick={() => void reload()}><RefreshCw className="h-4 w-4" /></button>
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
              <div><div className="font-medium">{item.name}</div><code className="text-xs text-muted-foreground">{item.key_prefix}…</code><div className="text-xs text-muted-foreground">{item.scopes.join(", ")}</div></div>
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
        <h2 className="font-semibold">接口目录</h2>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {catalog.map((item) => <div key={item.endpoint_code} className="rounded border p-3 text-sm"><code>{item.endpoint_code}</code><div className="text-xs text-muted-foreground">{item.dataset_group} · {item.pricing_mode} · 基础 {item.base_cost} 分</div></div>)}
        </div>
      </section>

      {secret && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
          <div className="w-full max-w-xl rounded-xl bg-background p-6 shadow-xl">
            <h2 className="font-semibold">保存你的 Data Hub Key</h2>
            <p className="mt-2 text-sm text-amber-600">该密钥仅显示一次，关闭后无法再次查看。</p>
            <div className="mt-4 flex items-center gap-2 rounded-lg border bg-muted p-3"><code className="min-w-0 flex-1 break-all">{secret.plaintext}</code><button aria-label="复制 Key" onClick={() => void navigator.clipboard?.writeText(secret.plaintext)}><Copy className="h-4 w-4" /></button></div>
            <button className="mt-5 rounded-md bg-primary px-4 py-2 text-primary-foreground" onClick={() => setSecret(null)}>我已保存</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="rounded-xl border bg-card p-5"><div className="text-xs text-muted-foreground">{label}</div><div className="mt-1 text-2xl font-bold">{value}</div>{detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}</div>;
}
