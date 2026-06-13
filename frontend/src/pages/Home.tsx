import { Link } from "react-router-dom";
import { ArrowRight, Bot, BarChart3, Zap, UserCircle2 } from "lucide-react";

export function Home() {
  const FEATURES = [
    { icon: Bot, title: "AI 智能体", desc: "自然语言描述策略，ReAct 推理自动生成代码并回测" },
    { icon: BarChart3, title: "内置回测引擎", desc: "覆盖A股、美股港股、加密货币，7大数据源" },
    { icon: Zap, title: "实时流式交互", desc: "实时观看智能体思考、调用工具、迭代优化" },
    { icon: UserCircle2, title: "交易复盘", desc: "交易记录分析 + 影子账户——提取交易规则、回测验证、盈亏归因" },
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8">
      <div className="max-w-2xl text-center space-y-6">
        <h1 className="text-4xl font-bold tracking-tight">AI 驱动的量化策略研究</h1>
        <p className="text-lg text-muted-foreground">用自然语言描述交易策略，智能体自动生成代码、运行回测并优化——全程实时可见。</p>
        <Link
          to="/agent"
          className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 transition"
        >
          开始研究 <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mt-16 max-w-5xl w-full">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="border rounded-lg p-6 space-y-3">
            <Icon className="h-8 w-8 text-primary" />
            <h3 className="font-semibold">{title}</h3>
            <p className="text-sm text-muted-foreground">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
