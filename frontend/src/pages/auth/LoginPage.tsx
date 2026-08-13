import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, LogIn, Monitor } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { setToken, setUser } from "@/lib/apiAuth";
import { SigmXLogo } from "@/components/brand/SigmXLogo";

function isDesktopMode(): boolean {
  return !!window.sigmxDesktop?.isDesktop;
}

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const desktop = isDesktopMode();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password || loading) return;
    setLoading(true);
    try {
      const res = await api.login(email.trim(), password);
      setToken(res.token);
      setUser(res.user);
      toast.success("登录成功");
      // RequireAuth will route to disclaimer modal if not yet accepted,
      // otherwise to the home page.
      navigate("/app");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const desktopContinue = async () => {
    setLoading(true);
    try {
      const res = await api.desktopSession();
      setToken(res.token);
      setUser(res.user);
      toast.success("已进入桌面模式");
      navigate("/app");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "桌面会话创建失败，请手动登录");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-2">
          <SigmXLogo className="h-10 w-10" />
          <h1 className="text-xl font-bold">SigmX 登录</h1>
        </div>

        {desktop && (
          <div className="mb-4 rounded-xl border border-primary/30 bg-primary/5 p-4">
            <p className="mb-3 text-center text-sm text-muted-foreground">
              检测到桌面客户端，可以免密进入
            </p>
            <button
              type="button"
              disabled={loading}
              onClick={desktopContinue}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Monitor className="h-4 w-4" />}
              进入桌面模式
            </button>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              或使用邮箱密码登录
            </p>
          </div>
        )}

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
            <label className="text-xs font-medium text-muted-foreground">密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••"
              required
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
            登录
          </button>
          <p className="text-center text-xs text-muted-foreground">
            还没有账号？{" "}
            <Link to="/register" className="font-medium text-primary hover:underline">立即注册</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
