import { beforeEach, describe, expect, it } from "vitest";

import { canGenerateRecommendationsLocally, resolveDataHubApiPath, setDataMode } from "@/lib/dataMode";


describe("resolveDataHubApiPath", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("keeps legacy paths in standalone mode", () => {
    setDataMode("standalone");

    expect(resolveDataHubApiPath("/market-dashboard/stages/morning-brief")).toBe(
      "/market-dashboard/stages/morning-brief",
    );
    expect(resolveDataHubApiPath("/daily-recommendations?status=final")).toBe(
      "/daily-recommendations?status=final",
    );
  });

  it("maps connected dashboard and recommendation reads to api v1", () => {
    setDataMode("connected");

    expect(resolveDataHubApiPath("/market-dashboard")).toBe("/api/v1/market-dashboard");
    expect(resolveDataHubApiPath("/market-dashboard/bars/000001.SH?days=60")).toBe(
      "/api/v1/market-dashboard/bars/000001.SH?days=60",
    );
    expect(resolveDataHubApiPath("/daily-recommendations?status=final")).toBe(
      "/api/v1/recommendations?status=final",
    );
    expect(resolveDataHubApiPath("/daily-recommendations/backtest?days=30")).toBe(
      "/api/v1/recommendations/backtest?days=30",
    );
  });

  it("keeps manual recommendation generation local", () => {
    setDataMode("connected");

    expect(resolveDataHubApiPath("/daily-recommendations/generate")).toBe(
      "/daily-recommendations/generate",
    );
  });

  it("allows manual recommendation generation only in standalone mode", () => {
    setDataMode("standalone");
    expect(canGenerateRecommendationsLocally()).toBe(true);

    setDataMode("connected");
    expect(canGenerateRecommendationsLocally()).toBe(false);
  });
});
