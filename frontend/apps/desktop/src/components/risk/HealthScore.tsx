import { cn } from "@/lib/utils";

export function HealthScore({ score }: { score: number | null }) {
  // 无持仓/未监控：不画分数，显示灰色占位，避免误读为"满分健康"
  if (score === null || score === undefined) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 p-6 flex flex-col items-center">
        <div className="text-sm text-white/50 mb-2">持仓健康评分</div>
        <div className="relative w-36 h-36 flex items-center justify-center">
          <div className="text-center">
            <div className="text-2xl font-bold text-white/30">—</div>
            <div className="text-xs text-white/40 mt-1">未持仓</div>
            <div className="text-xs text-white/40">未监控</div>
          </div>
        </div>
      </div>
    );
  }

  const clampedScore = Math.max(0, Math.min(100, score));
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const progress = (clampedScore / 100) * circumference;
  const dashoffset = circumference - progress;

  // Color gradient: red(0-30) → yellow(30-60) → green(60-100)
  let color = "text-red-400";
  let strokeColor = "#f87171";
  let label = "高风险";
  if (clampedScore >= 60) {
    color = "text-green-400";
    strokeColor = "#4ade80";
    label = "健康";
  } else if (clampedScore >= 30) {
    color = "text-yellow-400";
    strokeColor = "#facc15";
    label = "注意";
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-6 flex flex-col items-center">
      <div className="text-sm text-white/50 mb-2">持仓健康评分</div>
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 140 140">
          <circle
            cx="70" cy="70" r={radius}
            fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="12"
          />
          <circle
            cx="70" cy="70" r={radius}
            fill="none" stroke={strokeColor} strokeWidth="12"
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-3xl font-bold", color)}>
            {clampedScore.toFixed(0)}
          </span>
          <span className={cn("text-xs", color)}>{label}</span>
        </div>
      </div>
    </div>
  );
}
