import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronDown, Loader2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { setToken, setUser } from "@/lib/apiAuth";
import { SigmXLogo } from "@/components/brand/SigmXLogo";
import {
  DISCLAIMER_AGREE_LABEL, DISCLAIMER_BODY, DISCLAIMER_NOTE,
  DISCLAIMER_NOTE_TITLE, DISCLAIMER_TITLE,
} from "@/lib/disclaimer";

export function RegisterPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agree, setAgree] = useState(false);
  const [showDisclaimer, setShowDisclaimer] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    if (password.length < 6) {
      toast.error("密码至少 6 位");
      return;
    }
    if (password !== confirm) {
      toast.error("两次密码不一致");
      return;
    }
    if (!agree) {
      toast.error("请先勾选同意免责声明");
      return;
    }
    setLoading(true);
    try {
      const res = await api.register(email.trim(), password, agree);
      setToken(res.token);
      setUser(res.user);
      toast.success("注册成功");
      // New user has disclaimer_accepted_at = null → RequireAuth shows the modal.
      navigate("/");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <SigmXLogo className="h-10 w-10" />
          <h1 className="text-xl font-bold">注册 SigmX</h1>
        </div>

        <form onSubmit={submit} className="space-y-4 rounded-xl border bg-card p-6 shadow-sm">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">邮箱</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">密码（至少 6 位）</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••"
              required
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">确认密码</label>
            <input
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="••••••"
              required
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>

          {/* Disclaimer checkbox + collapsible full text */}
          <div className="rounded-lg border bg-muted/30 p-3">
            <label className="flex items-start gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={agree}
                onChange={e => setAgree(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-border"
              />
              <span className="flex-1">
                我已阅读并同意
                <button
                  type="button"
                  onClick={() => setShowDisclaimer(s => !s)}
                  className="ml-1 font-medium text-primary hover:underline"
                >
                  《{DISCLAIMER_TITLE}》
                </button>
              </span>
            </label>
            {showDisclaimer && (
              <div className="mt-2 space-y-2 border-t pt-2 text-[11px] leading-relaxed text-muted-foreground">
                <p className="text-foreground">{DISCLAIMER_BODY}</p>
                <p className="font-semibold text-foreground">{DISCLAIMER_NOTE_TITLE}</p>
                <p>{DISCLAIMER_NOTE}</p>
              </div>
            )}
            <button
              type="button"
              onClick={() => setShowDisclaimer(s => !s)}
              className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <ChevronDown className={`h-3 w-3 transition-transform ${showDisclaimer ? "rotate-180" : ""}`} />
              {showDisclaimer ? "收起" : "查看全文"}
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            注册
          </button>
          <p className="text-center text-xs text-muted-foreground">
            已有账号？{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">去登录</Link>
          </p>
          <p className="text-center text-[10px] text-muted-foreground/70">
            {DISCLAIMER_AGREE_LABEL}方可完成注册
          </p>
        </form>
      </div>
    </div>
  );
}
