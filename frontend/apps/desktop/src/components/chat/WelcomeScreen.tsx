import { TrendingUp, Globe, Sparkles, Users, UserCircle2, NotebookPen, Landmark } from "lucide-react";
import { SigmXLogo } from "@/components/brand/SigmXLogo";

interface Example {
  title: string;
  desc: string;
  prompt: string;
}

interface Category {
  label: string;
  icon: React.ReactNode;
  color: string;
  examples: Example[];
}

const CATEGORIES: Category[] = [
  {
    label: "多市场回测",
    icon: <TrendingUp className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "跨市场组合",
        desc: "A股 + 加密货币 + 美股，风险平价优化器",
        prompt: "Backtest a risk-parity portfolio of 000001.SZ, BTC-USDT, and AAPL for full-year 2024, compare against equal-weight baseline",
      },
      {
        title: "BTC 5分钟 MACD 策略",
        desc: "分钟级加密货币回测，OKX 实时数据",
        prompt: "Backtest BTC-USDT 5-minute MACD strategy, fast=12 slow=26 signal=9, last 30 days",
      },
      {
        title: "美股科技最大分散化",
        desc: "FAANG+ 组合优化器，yfinance 数据",
        prompt: "Backtest AAPL, MSFT, GOOGL, AMZN, NVDA with max_diversification portfolio optimizer, full-year 2024",
      },
    ],
  },
  {
    label: "研究与分析",
    icon: <Sparkles className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "多因子 Alpha 模型",
        desc: "IC 加权因子合成，覆盖 300 只股票",
        prompt: "Build a multi-factor alpha model using momentum, reversal, volatility, and turnover on CSI 300 constituents with IC-weighted factor synthesis, backtest 2023-2024",
      },
      {
        title: "期权 Greeks 分析",
        desc: "Black-Scholes 定价，Delta/Gamma/Theta/Vega",
        prompt: "Calculate option Greeks using Black-Scholes: spot=100, strike=105, risk-free rate=3%, vol=25%, expiry=90 days, analyze Delta/Gamma/Theta/Vega",
      },
    ],
  },
  {
    label: "智能体集群",
    icon: <Users className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "投资委员会评审",
        desc: "多智能体辩论：看多vs看空，风险评估，PM决策",
        prompt: "[Swarm Team Mode] Use the investment_committee preset to evaluate whether to go long or short on NVDA given current market conditions",
      },
      {
        title: "量化策略桌",
        desc: "筛选 → 因子研究 → 回测 → 风险审计流水线",
        prompt: "[Swarm Team Mode] Use the quant_strategy_desk preset to find and backtest the best momentum strategy on CSI 300 constituents",
      },
    ],
  },
  {
    label: "文档与网页研究",
    icon: <Globe className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "分析财报 PDF",
        desc: "上传 PDF，提问财务数据相关问题",
        prompt: "Summarize the key financial metrics, risks, and outlook from the uploaded earnings report",
      },
      {
        title: "网页研究：宏观展望",
        desc: "阅读实时网页来源进行宏观分析",
        prompt: "Read the latest Fed meeting minutes and summarize the key takeaways for equity and crypto markets",
      },
    ],
  },
  {
    label: "交易日志分析",
    icon: <NotebookPen className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "分析券商导出文件",
        desc: "解析同花顺/东财/富途/通用 CSV — 持仓天数、胜率、盈亏比、时段分布",
        prompt: "Analyze the trade journal I just uploaded — full profile with holding stats, win rate, top symbols, and hourly distribution",
      },
      {
        title: "交易行为诊断",
        desc: "处置效应、过度交易、追涨杀跌、锚定偏差 — 严重度 + 数据证据",
        prompt: "Run the 4 behavior diagnostics on my trade journal (disposition, overtrading, chasing, anchoring) and tell me which bias hurts my PnL most",
      },
    ],
  },
  {
    label: "交易连接器",
    icon: <Landmark className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "检查已选连接器",
        desc: "列出连接器配置并验证当前选择",
        prompt: "List my trading connector profiles, show which one is selected, then check that selected connector. If it is not ready, tell me exactly what setup step is missing. Do not place or modify orders.",
      },
      {
        title: "分析连接器持仓",
        desc: "从已选连接器读取账户摘要和持仓",
        prompt: "Use the selected trading connector profile to summarize my account, positions, concentration, cash, and portfolio risk. Do not place or modify orders.",
      },
      {
        title: "报价与趋势",
        desc: "通过连接器获取报价和近期日线数据",
        prompt: "Use the selected trading connector to fetch an AAPL quote and 30 daily bars, then summarize the current quote versus the recent trend. Keep it read-only.",
      },
    ],
  },
  {
    label: "影子账户",
    icon: <UserCircle2 className="h-4 w-4" />,
    color: "text-primary border-border hover:border-primary/50 hover:bg-primary/5",
    examples: [
      {
        title: "从交易日志训练影子",
        desc: "从券商 CSV 提取策略规则，持久化影子配置",
        prompt: "Train my shadow account from the trading journal I just uploaded — show the extracted rules and confirm they look like my behavior",
      },
      {
        title: "我少赚了多少？",
        desc: "回测影子策略，与实盘盈亏对照归因",
        prompt: "Run a shadow backtest for the last 90 days on the US market and break down where my PnL diverged from the shadow (rule violations, early exits, missed signals)",
      },
      {
        title: "生成影子报告",
        desc: "8 章节 HTML/PDF — 净值曲线、分市场夏普、归因瀑布图",
        prompt: "Render the shadow report and give me the URL — lead with the you-vs-shadow delta",
      },
    ],
  },
];

const CAPABILITY_CHIPS = [
  "77 个金融技能库",
  "29 个智能体集群",
  "自动发现工具",
  "三大市场：A股 · 加密货币 · 港股美股",
  "交易连接器配置",
  "分钟级到日线级",
  "4 种组合优化器",
  "15+ 风险指标",
  "期权与衍生品",
  "文档与网页研究",
  "因子分析与机器学习",
  "交易日志分析器",
  "影子账户回测",
  "持久化记忆",
  "会话搜索",
];

interface Props {
  onExample: (s: string) => void;
}

export function WelcomeScreen({ onExample }: Props) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] space-y-8 text-center">
      {/* Header */}
      <div className="space-y-3">
        <div className="mx-auto flex h-16 w-16 items-center justify-center">
          <SigmXLogo className="h-16 w-16 drop-shadow-lg" />
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight">SigmX</h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto leading-relaxed">
            与专业金融智能体团队一起进行直觉交易
          </p>
          <p className="text-sm text-muted-foreground mt-2 max-w-md leading-relaxed mx-auto">
            描述一个交易策略即可开始。
          </p>
        </div>
      </div>

      {/* Capability chips */}
      <div className="flex flex-wrap justify-center gap-2 max-w-lg">
        {CAPABILITY_CHIPS.map((chip) => (
          <span
            key={chip}
            className="px-2.5 py-1 text-xs rounded-full border border-border/60 text-muted-foreground bg-muted/30"
          >
            {chip}
          </span>
        ))}
      </div>

      {/* Example categories grid */}
      <div className="w-full max-w-2xl text-left space-y-4">
        <p className="text-xs text-muted-foreground px-1">试试这些例子：</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {CATEGORIES.map((cat) => (
            <div key={cat.label} className="space-y-2">
              <div className={`flex items-center gap-1.5 text-xs font-medium px-1 ${cat.color.split(" ").filter(c => c.startsWith("text-")).join(" ")}`}>
                {cat.icon}
                <span>{cat.label}</span>
              </div>
              <div className="space-y-1.5">
                {cat.examples.map((ex) => (
                  <button
                    key={ex.title}
                    onClick={() => onExample(ex.prompt)}
                    className={`block w-full text-left px-3 py-2.5 rounded-md border bg-card transition-colors ${cat.color}`}
                  >
                    <span className="text-sm font-medium text-foreground leading-snug">
                      {ex.title}
                    </span>
                    <span className="block text-xs text-muted-foreground mt-0.5 leading-snug">
                      {ex.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
