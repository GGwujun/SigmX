import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Coins, Gift, KeyRound, Loader2, LogOut, RefreshCw, User,
} from "lucide-react";
import { toast } from "sonner";
import { api, type AccountInfo, type CreditTransaction } from "@/lib/api";
import { clearAuth, setUser } from "@/lib/apiAuth";
import { cn } from "@/lib/utils";

const TX_TYPE_LABEL: Record<string, string> = {
  redeem: "兑换",
  consume: "消费",
  refund: "退还",
  admin: "调整",
};

function shortDate(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function Account() {
  const navigate = useNavigate();
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [transactions, setTransactions] = useState<CreditTransaction[]>([]);

  // redeem form
  const [code, setCode] = useState("");
  const [redeeming, setRedeeming] = useState(false);

  // change password form
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [changingPwd, setChangingPwd] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [acc, tx] = await Promise.all([api.getAccount(), api.getTransactions(50)]);
      setAccount(acc);
      // keep local user in sync (balance not stored there, but id/email current)
      setUser({ id: acc.id, email: acc.email, disclaimer_accepted_at: acc.disclaimer_accepted_at, created_at: acc.created_at });
      setTransactions(tx.items || []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const doRedeem = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim() || redeeming) return;
    setRedeeming(true);
    try {
      const res = await api.redeemCode(code.trim());
      toast.success(res.message || `兑换成功 +${res.credits}`);
      setCode("");
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "兑换失败");
    } finally {
      setRedeeming(false);
    }
  };

  const doChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    if (changingPwd) return;
    if (newPwd.length < 6) { toast.error("新密码至少 6 位"); return; }
    if (newPwd !== confirmPwd) { toast.error("两次新密码不一致"); return; }
    setChangingPwd(true);
    try {
      await api.changePassword(oldPwd, newPwd);
      toast.success("密码已更新");
      setOldPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "修改失败");
    } finally {
      setChangingPwd(false);
    }
  };

  const logout = () => {
    clearAuth();
    toast.info("已退出登录");
    navigate("/login", { replace: true });
  };

  if (loading || !account) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <header className="border-b px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <User className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold">个人中心</h1>
            <p className="text-xs text-muted-foreground">账户信息 · 积分 · 兑换码 · 消费记录</p>
          </div>
        </div>
        <button onClick={() => reload()} className="p-2 rounded-lg hover:bg-muted transition-colors" title="刷新">
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Account info + balance */}
          <section className="rounded-xl border bg-card p-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">账户信息</div>
                <div className="text-sm"><span className="text-muted-foreground">邮箱</span> · {account.email}</div>
                <div className="text-sm font-mono text-xs"><span className="text-muted-foreground font-sans">ID</span> · {account.id}</div>
                <div className="text-sm"><span className="text-muted-foreground">注册时间</span> · {shortDate(account.created_at)}</div>
              </div>
              <div className="flex flex-col items-start justify-center rounded-lg bg-primary/5 border border-primary/15 p-4">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Coins className="h-3.5 w-3.5" /> 积分余额
                </div>
                <div className="mt-1 text-3xl font-bold text-primary tabular-nums">{account.balance}</div>
              </div>
            </div>
            <div className="mt-4 border-t pt-4">
              <button onClick={logout} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-danger/40 text-danger text-sm hover:bg-danger/5">
                <LogOut className="h-3.5 w-3.5" /> 退出登录
              </button>
            </div>
          </section>

          {/* Redeem code */}
          <section className="rounded-xl border bg-card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Gift className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">兑换积分</h2>
            </div>
            <form onSubmit={doRedeem} className="flex gap-2">
              <input
                value={code}
                onChange={e => setCode(e.target.value)}
                placeholder="输入兑换码，如 SIGMX-XXXX-XXXX"
                disabled={redeeming}
                className="flex-1 px-3 py-2 rounded-lg border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              <button type="submit" disabled={!code.trim() || redeeming}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-40">
                {redeeming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Gift className="h-4 w-4" />}
                兑换
              </button>
            </form>
          </section>

          {/* Change password */}
          <section className="rounded-xl border bg-card p-5">
            <div className="flex items-center gap-2 mb-3">
              <KeyRound className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">修改密码</h2>
            </div>
            <form onSubmit={doChangePassword} className="space-y-3">
              <input type="password" value={oldPwd} onChange={e => setOldPwd(e.target.value)} placeholder="原密码"
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              <input type="password" value={newPwd} onChange={e => setNewPwd(e.target.value)} placeholder="新密码（至少 6 位）"
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              <input type="password" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)} placeholder="确认新密码"
                className="w-full px-3 py-2 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
              <button type="submit" disabled={changingPwd || !oldPwd || !newPwd}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm font-medium hover:bg-muted disabled:opacity-40">
                {changingPwd ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                更新密码
              </button>
            </form>
          </section>

          {/* Transactions */}
          <section className="rounded-xl border bg-card p-5">
            <div className="flex items-center gap-2 mb-3">
              <Coins className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">积分流水</h2>
            </div>
            {transactions.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">暂无记录</p>
            ) : (
              <div className="overflow-hidden rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/40 text-xs text-muted-foreground">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">时间</th>
                      <th className="text-left px-3 py-2 font-medium">类型</th>
                      <th className="text-right px-3 py-2 font-medium">变动</th>
                      <th className="text-right px-3 py-2 font-medium">余额</th>
                      <th className="text-left px-3 py-2 font-medium">说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map(t => (
                      <tr key={t.id} className="border-t">
                        <td className="px-3 py-2 text-xs text-muted-foreground">{shortDate(t.created_at)}</td>
                        <td className="px-3 py-2">{TX_TYPE_LABEL[t.type] || t.type}</td>
                        <td className={cn("px-3 py-2 text-right font-mono", t.delta > 0 ? "text-success" : "text-danger")}>
                          {t.delta > 0 ? "+" : ""}{t.delta}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-muted-foreground">{t.balance_after}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground truncate max-w-[200px]">{t.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
