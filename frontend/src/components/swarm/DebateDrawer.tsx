import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DebateClaim {
  claim_id: string;
  speaker: string;
  speaker_key: string;
  stance: string;
  claim: string;
  evidence: string[];
  confidence: number;
  status: string;
  target_claim_ids: string[];
  round_index: number;
}

export interface DebateUpdate {
  agent: string;
  task_id: string;
  payload: {
    new_claims?: Array<{
      claim: string;
      evidence: string[];
      confidence: number;
      target_claim_ids: string[];
    }>;
    responded_claim_ids?: string[];
    resolved_claim_ids?: string[];
    unresolved_claim_ids?: string[];
    round_summary?: string;
    speaker_key?: string;
  };
  timestamp: string;
}

const SPEAKER_CONFIG: Record<string, { label: string; emoji: string; color: string }> = {
  bull: { label: "多头", emoji: "🐂", color: "text-green-400 bg-green-500/10 border-green-500/20" },
  bear: { label: "空头", emoji: "🐻", color: "text-red-400 bg-red-500/10 border-red-500/20" },
  neutral: { label: "仲裁", emoji: "⚖️", color: "text-blue-400 bg-blue-500/10 border-blue-500/20" },
};

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  open: { label: "待回应", color: "bg-blue-500/20 text-blue-300" },
  addressed: { label: "已回应", color: "bg-yellow-500/20 text-yellow-300" },
  resolved: { label: "已解决", color: "bg-green-500/20 text-green-300" },
  unresolved: { label: "未解决", color: "bg-red-500/20 text-red-300" },
};

export function DebateDrawer({
  updates,
  open,
  onClose,
}: {
  updates: DebateUpdate[];
  open: boolean;
  onClose: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [updates, autoScroll]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 80);
  };

  if (!open) return null;

  // Group by round (speaker_key changes indicate new round)
  const rounds: Map<number, DebateUpdate[]> = new Map();
  for (const u of updates) {
    const round = rounds.size + 1;
    const existing = rounds.get(round) || [];
    existing.push(u);
    rounds.set(round, existing);
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-gray-900 border-l border-white/10 shadow-2xl flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <span className="text-lg">🐂⚔️🐻</span>
          <h3 className="text-sm font-semibold text-white/80">多空辩论实况</h3>
          <span className="text-xs text-white/40">{updates.length} 次更新</span>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/10 transition">
          <X className="h-4 w-4 text-white/60" />
        </button>
      </div>

      {/* Content */}
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-4 space-y-4">
        {updates.length === 0 && (
          <div className="text-center text-sm text-white/40 py-8">
            等待辩论开始…
          </div>
        )}

        {updates.map((u, idx) => {
          const speakerKey = u.payload.speaker_key || deriveSpeakerKey(u.agent);
          const config = SPEAKER_CONFIG[speakerKey] || SPEAKER_CONFIG.neutral;
          const newClaims = u.payload.new_claims || [];
          const responded = u.payload.responded_claim_ids || [];
          const summary = u.payload.round_summary || "";

          return (
            <div key={idx} className="space-y-2">
              {/* Agent header */}
              <div className={cn("rounded-lg border px-3 py-2", config.color)}>
                <span className="text-sm font-semibold">
                  {config.emoji} {u.agent}
                </span>
                <span className="text-xs text-white/40 ml-2">
                  {u.timestamp?.replace("T", " ").slice(0, 19)}
                </span>
              </div>

              {/* Responded claims */}
              {responded.length > 0 && (
                <div className="text-xs text-white/50 pl-3">
                  回应: {responded.join(", ")}
                </div>
              )}

              {/* New claims */}
              {newClaims.map((c, ci) => {
                // 从已知的 claim 中查找实际状态（如果有）
                const claimId = `${speakerKey.toUpperCase()}-${ci + 1}`;
                const resolvedIds = new Set([
                  ...(u.payload.responded_claim_ids || []),
                ]);
                const status = resolvedIds.has(claimId) ? "addressed" : "open";
                const badge = STATUS_BADGE[status] || STATUS_BADGE.open;
                return (
                  <div key={ci} className="rounded-lg border border-white/10 bg-white/5 p-3 ml-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm text-white/80 font-medium">{c.claim}</div>
                      <span className={cn("text-xs px-1.5 py-0.5 rounded flex-shrink-0", badge.color)}>
                        {badge.label}
                      </span>
                    </div>
                    {c.evidence?.length > 0 && (
                      <div className="mt-2 space-y-0.5">
                        {c.evidence.slice(0, 3).map((e, ei) => (
                          <div key={ei} className="text-xs text-white/50">• {e}</div>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 flex items-center gap-3 text-xs text-white/40">
                      <span>置信度 {(c.confidence * 100).toFixed(0)}%</span>
                      {c.target_claim_ids?.length > 0 && (
                        <span>反驳: {c.target_claim_ids.join(", ")}</span>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Round summary */}
              {summary && (
                <div className="text-xs text-white/50 pl-3 italic">「{summary}」</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer: auto-scroll indicator */}
      {!autoScroll && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
          }}
          className="absolute bottom-4 right-4 rounded-full bg-blue-500/20 border border-blue-500/30 px-3 py-1.5 text-xs text-blue-400 hover:bg-blue-500/30 transition"
        >
          ↓ 滚动到底部
        </button>
      )}
    </div>
  );
}

function deriveSpeakerKey(agentId: string): string {
  if (agentId.includes("bull")) return "bull";
  if (agentId.includes("bear")) return "bear";
  if (agentId.includes("neutral")) return "neutral";
  return "neutral";
}
