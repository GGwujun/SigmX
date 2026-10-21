/**
 * Risk-engine API response types (regime + layered risk checks). Owned by the
 * API layer so both the API surface and consumers share one definition.
 */
export interface RegimeData {
  trade_date: string;
  regime: string;
  confidence: number;
  bull_score: number;
  bear_score: number;
  strong_trend: boolean;
  technical_indicators: Record<string, unknown>;
  parameters: Record<string, unknown>;
}

export interface RiskCheck {
  layer: number;
  name: string;
  triggered: boolean;
  severity: string;
  message: string;
  details: Record<string, unknown>;
  action: string;
}

export interface RiskCheckData {
  trade_date: string;
  regime: string;
  checks: RiskCheck[];
  portfolio_health_score: number | null;
  has_positions: boolean;
  summary: string;
}

export interface RiskEvent {
  event_id: string;
  trade_date: string;
  layer: number;
  severity: string;
  code: string | null;
  message: string;
  created_at: string;
}
