import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { setToken, setUser } from "@/lib/apiAuth";
import { PublicLayout } from "../PublicLayout";

describe("PublicLayout", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("presents separate discovery and intelligence destinations", () => {
    render(<MemoryRouter><PublicLayout /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "AI 发现" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "情报搜索" })).toHaveAttribute("href", "/intelligence");
    expect(screen.getByRole("link", { name: "Desktop" })).toHaveAttribute("href", "/product/desktop");
    expect(screen.getByRole("link", { name: "Data Hub" })).toHaveAttribute("href", "/product/data-hub");
  });

  it("shows the account entry instead of registration for a signed-in user", () => {
    setToken("test-token");
    setUser({ id: "1", email: "admin@sigmx.local", created_at: "2026-08-23", disclaimer_accepted_at: null });

    render(<MemoryRouter><PublicLayout /></MemoryRouter>);

    expect(screen.getByRole("button", { name: /admin@sigmx.local/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "注册体验" })).not.toBeInTheDocument();
  });

  it("keeps the signed-in account menu above page overlays", () => {
    setToken("test-token");
    setUser({ id: "1", email: "admin@sigmx.local", created_at: "2026-08-23", disclaimer_accepted_at: null });

    render(<MemoryRouter><PublicLayout /></MemoryRouter>);

    expect(screen.getByRole("banner")).toHaveClass("z-40", "bg-background");
    expect(screen.getByRole("banner")).not.toHaveClass("bg-background/95");
  });

  it("opens a complete account menu and only exposes operations to admins", async () => {
    setToken("test-token");
    setUser({ id: "1", email: "admin@sigmx.local", created_at: "2026-08-23", disclaimer_accepted_at: null, is_admin: true });
    render(<MemoryRouter><PublicLayout /></MemoryRouter>);

    await userEvent.click(screen.getByRole("button", { name: /admin@sigmx.local/ }));
    expect(screen.getByRole("menu")).toHaveClass("bg-background");
    expect(screen.getByRole("menu")).not.toHaveClass("bg-popover");
    expect(screen.getByRole("menuitem", { name: "个人中心" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("menuitem", { name: "账户与安全" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("menuitem", { name: "Data Hub 控制台" })).toHaveAttribute("href", "/account/data-hub");
    expect(screen.getByRole("menuitem", { name: "运营后台" })).toHaveAttribute("href", "/admin");
  });

  it("provides every primary destination in the mobile menu", async () => {
    render(<MemoryRouter><PublicLayout /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: "打开导航" }));
    for (const label of ["AI 发现", "情报搜索", "投研 Skills", "Desktop", "Data Hub", "套餐"]) {
      expect(screen.getAllByRole("link", { name: label }).length).toBeGreaterThan(0);
    }
  });

  it.each([
    ["/intelligence", "情报搜索"],
    ["/docs/data-hub/stocks.daily", "Data Hub"],
    ["/skills/value-dividend", "投研 Skills"],
    ["/query/低估值", "AI 发现"],
  ])("marks the owning navigation item active at %s", (path, label) => {
    render(<MemoryRouter initialEntries={[path]}><PublicLayout /></MemoryRouter>);
    expect(screen.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
  });
});
