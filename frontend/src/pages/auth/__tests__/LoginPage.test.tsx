import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { LoginPage } from "../LoginPage";
import { getToken } from "@/lib/apiAuth";

const AUTH_OK = {
  token: "jwt-abc",
  user: {
    id: "u1",
    email: "user@test.com",
    disclaimer_accepted_at: "2026-08-01",
    created_at: "2026-08-01",
    is_admin: false,
  },
};

function mockAuthFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => AUTH_OK,
      text: async () => JSON.stringify(AUTH_OK),
    } as unknown as Response),
  );
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/portal" element={<div>portal-page</div>} />
        <Route path="/app" element={<div>workbench-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitLogin() {
  await userEvent.type(screen.getByPlaceholderText("you@example.com"), "user@test.com");
  await userEvent.type(screen.getByPlaceholderText("••••••"), "secret123");
  await userEvent.click(screen.getByRole("button", { name: /登录/ }));
}

describe("LoginPage post-login routing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("sends browsers to the light portal", async () => {
    mockAuthFetch();
    renderPage();
    await submitLogin();
    await waitFor(() => expect(getToken()).toBe("jwt-abc"));
    expect(await screen.findByText("portal-page")).toBeInTheDocument();
    expect(screen.queryByText("workbench-page")).not.toBeInTheDocument();
  });

  it("sends the desktop client to the workbench", async () => {
    vi.stubGlobal("sigmxDesktop", { isDesktop: true });
    mockAuthFetch();
    renderPage();
    await submitLogin();
    await waitFor(() => expect(getToken()).toBe("jwt-abc"));
    expect(await screen.findByText("workbench-page")).toBeInTheDocument();
  });
});
