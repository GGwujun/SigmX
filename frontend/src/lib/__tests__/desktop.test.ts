import { afterEach, describe, expect, it, vi } from "vitest";

import { isDesktopMode, postLoginTarget } from "../desktop";

describe("lib/desktop", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("defaults to browser mode when sigmxDesktop is absent", () => {
    expect(isDesktopMode()).toBe(false);
    expect(postLoginTarget()).toBe("/me");
  });

  it("detects desktop mode when preload injected isDesktop=true", () => {
    vi.stubGlobal("sigmxDesktop", { isDesktop: true });
    expect(isDesktopMode()).toBe(true);
    expect(postLoginTarget()).toBe("/app");
  });

  it("treats isDesktop absent as browser mode", () => {
    vi.stubGlobal("sigmxDesktop", {});
    expect(isDesktopMode()).toBe(false);
    expect(postLoginTarget()).toBe("/me");
  });
});
