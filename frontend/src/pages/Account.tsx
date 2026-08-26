import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  KeyRound, Loader2, LogOut, RefreshCw, User,
} from "lucide-react";
import { toast } from "sonner";
import { AccountPage } from "@/components/layout/AccountPage";
import { api, type AccountInfo } from "@/lib/api";
import { clearAuth, updateStoredUserProfile } from "@/lib/apiAuth";

function shortDate(value?: string | null): string {
  if (!value) return "—";
  return value.slice(0, 16).replace("T", " ");
}

export function Account() {
  const navigate = useNavigate();
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // change password form
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [changingPwd, setChangingPwd] = useState(false);

  const reload = useCallback(async () => {
    try {
      const acc = await api.getAccount();
      setAccount(acc);
      // keep local user in sync (balance not stored there, but id/email current)
      updateStoredUserProfile({ id: acc.id, email: acc.email, disclaimer_accepted_at: acc.disclaimer_accepted_at, created_at: acc.created_at });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

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
      <AccountPage>
        <div className="flex min-h-64 items-center justify-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      </AccountPage>
    );
  }

  return (
    <AccountPage>
    <div className="flex flex-col overflow-hidden">
      <header className="border-b px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <User className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold">账户与安全</h1>
            <p className="text-xs text-muted-foreground">管理登录身份与账户安全</p>
          </div>
        </div>
        <button onClick={() => reload()} className="p-2 rounded-lg hover:bg-muted transition-colors" title="刷新">
          <RefreshCw className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="space-y-6">
          {/* Account identity */}
          <section className="rounded-xl border bg-card p-5">
            <div className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">账户信息</div>
              <div className="text-sm"><span className="text-muted-foreground">邮箱</span> · {account.email}</div>
              <div className="text-xs font-mono"><span className="font-sans text-muted-foreground">账户 ID</span> · {account.id}</div>
              <div className="text-sm"><span className="text-muted-foreground">注册时间</span> · {shortDate(account.created_at)}</div>
            </div>
            <div className="mt-4 border-t pt-4">
              <button onClick={logout} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-danger/40 text-danger text-sm hover:bg-danger/5">
                <LogOut className="h-3.5 w-3.5" /> 退出登录
              </button>
            </div>
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

        </div>
      </div>
    </div>
    </AccountPage>
  );
}
