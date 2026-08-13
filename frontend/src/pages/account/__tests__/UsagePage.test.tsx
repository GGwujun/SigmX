import { describe, it, expect, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { UsagePage } from "../UsagePage";

afterEach(() => vi.restoreAllMocks());

function mockFetchByPath(map: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      for (const key of Object.keys(map)) {
        if (url.includes(key)) {
          return Promise.resolve({ ok: true, status: 200, json: async () => map[key] } as unknown as Response);
        }
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as unknown as Response);
    }),
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <UsagePage />
    </MemoryRouter>,
  );
}

describe("UsagePage", () => {
  it("shows consumed/quota/remaining from the server", async () => {
    mockFetchByPath({
      "/api/usage/me": {
        metric: "datahub.request",
        day: "2026-08-14",
        consumed: 150,
        quota_daily: 1000,
        remaining: 850,
      },
    });
    renderPage();
    expect(await screen.findByText(/150/)).toBeInTheDocument();
    expect(screen.getByText(/1,000/)).toBeInTheDocument();
    expect(screen.getByText(/剩余 850/)).toBeInTheDocument();
  });

  it("shows the empty/zero state for a new user", async () => {
    mockFetchByPath({
      "/api/usage/me": { metric: "datahub.request", day: "2026-08-14", consumed: 0, quota_daily: 0, remaining: 0 },
    });
    renderPage();
    await waitFor(() => {
      // consumed (0) and "剩余 0" both render.
      expect(screen.getByText(/剩余 0/)).toBeInTheDocument();
    });
  });
});
