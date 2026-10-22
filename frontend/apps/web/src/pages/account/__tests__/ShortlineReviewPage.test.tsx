import { describe, it, expect, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ShortlineReviewPage } from "../ShortlineReviewPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, text: async () => JSON.stringify(body) } as unknown as Response;
}

const REVIEW = {
  id: "r1",
  trade_date: "2026-10-21",
  model: "glm-4.7",
  status: "completed",
  sections: {
    sentiment: { text: "情绪修复。", retries: 0, audit: {}, gate_ok: true, gate_hits: 0, unknown_citations: 0 },
    summary: { text: "汇总段。", retries: 1, audit: {}, gate_ok: false, gate_hits: 1, unknown_citations: 0 },
  },
  gaps: ["capital/资金快照缺失"],
  conditions: [
    { metric: "limit_up_count", direction: "up", note: "情绪修复延续",
      verification: { status: "verified", prev_value: 53, cur_value: 71, actual: "up", late: 0,
                      checked_at: "2026-10-22T15:10:00+08:00", written_at: "2026-10-21T18:00:00+08:00" } },
    { metric: "turnover_total_yi", direction: "flat", note: "缩量企稳",
      verification: { status: "pending", prev_value: null, cur_value: null, actual: null, late: 0,
                      checked_at: null, written_at: "2026-10-21T18:00:00+08:00" } },
  ],
  error: null,
  created_at: "2026-10-21T18:05:00+08:00",
  finished_at: "2026-10-21T18:09:00+08:00",
};

const TRACK = {
  window_days: 60,
  metric: null,
  decided: 14,
  hits: 9,
  hit_rate: 0.6429,
  by_metric: {
    limit_up_count: {
      decided: 14, hits: 9, hit_rate: 0.6429,
      by_direction: {
        up: { decided: 14, hits: 9, expected_rate: 0.52, baseline_sample: 40, edge: 1.72 },
      },
    },
  },
};

function mockFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/shortline/review/latest")) return jsonResponse(REVIEW);
      if (url.includes("/shortline/review/track")) return jsonResponse(TRACK);
      throw new Error(`unexpected fetch: ${url}`);
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ShortlineReviewPage />
    </MemoryRouter>,
  );
}

describe("ShortlineReviewPage", () => {
  it("renders the latest review sections with audit warnings and gaps", async () => {
    mockFetch();
    renderPage();

    expect(await screen.findByText("2026-10-21")).toBeInTheDocument();
    expect(screen.getByText(/情绪修复。/)).toBeInTheDocument();
    expect(screen.getByText(/汇总段。/)).toBeInTheDocument();
    expect(screen.getByText(/合规 gate 命中 1 处/)).toBeInTheDocument();
    expect(screen.getByText(/数据缺口：capital\/资金快照缺失/)).toBeInTheDocument();
  });

  it("renders condition verification states from the machine-checked table", async () => {
    mockFetch();
    renderPage();

    // 「命中」同时出现在条件徽标与战绩表头——用徽标样式定位
    const badge = await screen.findByText("命中", { selector: "span" });
    expect(badge).toHaveClass("text-emerald-600");
    expect(screen.getByText("待对账")).toBeInTheDocument();
    expect(screen.getAllByText("涨停数").length).toBeGreaterThan(0);
    expect(screen.getAllByText("看涨").length).toBeGreaterThan(0);
    expect(screen.getByText("53 → 71")).toBeInTheDocument();
  });

  it("renders the track record with baseline-corrected edge", async () => {
    mockFetch();
    renderPage();

    expect(await screen.findByText(/基准发生率/)).toBeInTheDocument();
    expect(screen.getByText("52%（n=40）")).toBeInTheDocument();
    expect(screen.getByText("+1.72")).toBeInTheDocument();
  });

  it("shows an empty-state prompt when no review exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/shortline/review/latest")) return jsonResponse(null);
        if (url.includes("/shortline/review/track")) {
          return jsonResponse({ window_days: 60, metric: null, decided: 0, hits: 0, hit_rate: null, by_metric: {} });
        }
        throw new Error(`unexpected fetch: ${url}`);
      }),
    );
    renderPage();

    expect(await screen.findByText(/还没有复盘记录/)).toBeInTheDocument();
  });
});
