import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { PortalLayout } from "../PortalLayout";
import { getToken } from "@/lib/apiAuth";

function setStoredUser(isAdmin: boolean) {
  window.localStorage.setItem(
    "sigmx_user",
    JSON.stringify({ id: "u1", email: "user@test.com", is_admin: isAdmin, disclaimer_accepted_at: "2026-08-01" }),
  );
  window.localStorage.setItem("sigmx_auth_token", "jwt-1");
}

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/account"]}>
      <Routes>
        <Route element={<PortalLayout />}>
          <Route path="/account" element={<div>portal-body</div>} />
        </Route>
        <Route path="/login" element={<div>login-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PortalLayout", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the header and the outlet content for regular users", () => {
    setStoredUser(false);
    renderLayout();
    expect(screen.getByRole("link", { name: "SigmX" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("link", { name: "我的 SigmX" })).toBeInTheDocument();
    expect(screen.getByText("user@test.com")).toBeInTheDocument();
    expect(screen.getByText("portal-body")).toBeInTheDocument();
    expect(screen.queryByText("运营后台")).not.toBeInTheDocument();
  });

  it("shows the operations entry for admins", () => {
    setStoredUser(true);
    renderLayout();
    expect(screen.getByText("运营后台")).toBeInTheDocument();
  });

  it("clears credentials and leaves to /login on logout", async () => {
    setStoredUser(false);
    renderLayout();
    await userEvent.click(screen.getByText("退出"));
    expect(getToken()).toBe("");
    expect(window.localStorage.getItem("sigmx_user")).toBeNull();
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });
});
