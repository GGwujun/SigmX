/**
 * Desktop client product-boundary page (design §7.1 /product/desktop, §2.3).
 * Explains Standalone vs Connected modes and what stays local. Static content.
 */
import { Link } from "react-router-dom";
import { ArrowRight, Check, Monitor, Plug, Unplug } from "lucide-react";

const LOCAL = [
  "私有持仓、自选股、交易日志与上传文件",
  "本地报告、策略、回测与定时任务",
  "用户自带的模型 Key 或本地模型",
  "本地提醒、通知与券商连接",
];

const MODES = [
  {
    icon: Unplug,
    name: "Standalone 模式",
    desc: "无需云账户或 Data Hub 连接。使用本地数据源，所有功能在本机运行。",
  },
  {
    icon: Plug,
    name: "Connected 模式",
    desc: "通过统一权益令牌访问 Data Hub。设备授权登录，不复制用户密码。",
  },
];

export function DesktopProductPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-16">
      <div className="mb-8 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
        <Monitor className="h-6 w-6 text-primary" />
      </div>
      <h1 className="text-3xl font-bold tracking-tight">桌面客户端</h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">
        本地优先的投研工作台。私有数据默认留在本机，云端不可用时本地功能不中断。
      </p>

      <section className="mt-10 rounded-xl border bg-card p-6">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-emerald-600">
          <Check className="h-4 w-4" /> 客户端本地保存（默认不同步）
        </h2>
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {LOCAL.map((l) => (
            <li key={l} className="flex gap-2">
              <span className="text-emerald-600">·</span>
              {l}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2">
        {MODES.map(({ icon: Icon, name, desc }) => (
          <div key={name} className="rounded-xl border bg-card p-6">
            <Icon className="h-5 w-5 text-primary" />
            <h3 className="mt-2 text-base font-semibold">{name}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
          </div>
        ))}
      </section>

      <div className="mt-10 rounded-2xl border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">
          注册后下载客户端，用同一账号登录即可连接 Data Hub。
        </p>
        <Link
          to="/register"
          className="mt-4 inline-flex h-10 items-center gap-1 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          注册下载 <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  );
}
