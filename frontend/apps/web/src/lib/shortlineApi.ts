/**
 * Typed client for the AI shortline review APIs (/api/v1/shortline/review/*).
 *
 * Mirrors productRequest's style: shares authHeaders() + ApiError. The review
 * itself is market-level; the endpoints still require a logged-in user.
 */
import { ApiError } from "@/lib/api";
import { authHeaders } from "@/lib/apiAuth";

// ---- Types matching src/api/shortline_review_routes.py ----

export interface ConditionVerification {
  status: "pending" | "verified" | "mismatch" | "no_data" | string;
  prev_value: number | null;
  cur_value: number | null;
  actual: string | null;
  late: number;
  checked_at: string | null;
  written_at: string;
}

export interface ReviewCondition {
  metric: string;
  direction: "up" | "down" | "flat" | string;
  note: string;
  verification?: ConditionVerification;
}

export interface ReviewSection {
  text: string;
  retries: number;
  audit: Record<string, unknown>;
  gate_ok: boolean;
  gate_hits: number;
  unknown_citations: number;
}

export interface ShortlineReview {
  id: string;
  trade_date: string;
  model: string | null;
  status: string;
  sections: Record<string, ReviewSection>;
  gaps: string[];
  conditions: ReviewCondition[];
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface VerifyResult {
  condition_date: string;
  verified_date: string;
  checked: number;
  verified: number;
  mismatch: number;
  no_data: number;
  late: number;
  remaining: number;
  [key: string]: unknown;
}

export interface TrackDirection {
  decided: number;
  hits: number;
  expected_rate?: number;
  baseline_sample?: number;
  edge?: number;
}

export interface TrackMetric {
  decided: number;
  hits: number;
  hit_rate: number | null;
  by_direction: Record<string, TrackDirection>;
}

export interface TrackRecord {
  window_days: number;
  metric: string | null;
  decided: number;
  hits: number;
  hit_rate: number | null;
  by_metric: Record<string, TrackMetric>;
}

async function shortlineRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(options?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* keep HTTP status */
    }
    throw new ApiError(detail, res.status);
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export function getLatestReview(tradeDate?: string): Promise<ShortlineReview | null> {
  const q = tradeDate ? `?trade_date=${encodeURIComponent(tradeDate)}` : "";
  return shortlineRequest<ShortlineReview | null>(`/api/v1/shortline/review/latest${q}`);
}

export function startReview(tradeDate?: string): Promise<ShortlineReview> {
  return shortlineRequest<ShortlineReview>("/api/v1/shortline/review", {
    method: "POST",
    body: JSON.stringify(tradeDate ? { trade_date: tradeDate } : {}),
  });
}

export function verifyConditions(tradeDate?: string): Promise<VerifyResult> {
  const q = tradeDate ? `?trade_date=${encodeURIComponent(tradeDate)}` : "";
  return shortlineRequest<VerifyResult>(`/api/v1/shortline/review/verify${q}`, {
    method: "POST",
  });
}

export function getTrackRecord(metric?: string, window = 60): Promise<TrackRecord> {
  const params = new URLSearchParams({ window: String(window) });
  if (metric) params.set("metric", metric);
  return shortlineRequest<TrackRecord>(
    `/api/v1/shortline/review/track?${params.toString()}`);
}

/** 展示名：白名单 metric → 中文标签（不在白名单的原样返回）。 */
export const METRIC_LABELS: Record<string, string> = {
  limit_up_count: "涨停数",
  limit_down_count: "跌停数",
  zt_highest_ladder: "最高连板",
  emotion_avg: "情绪均分",
  turnover_total_yi: "成交额（亿）",
  firstboard_total: "首板数",
  theme_count: "主题数",
  break_times: "炸板均次",
  zb_count: "炸板数",
};

export const DIRECTION_LABELS: Record<string, string> = {
  up: "看涨",
  down: "看跌",
  flat: "看平",
};
