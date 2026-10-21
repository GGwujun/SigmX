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

function renderPage(initial = "/login") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/me" element={<div>portal-home</div>} />
        <Route path="/app" element={<div>workbench-page</div>} />
        <Route path="/query/:id" element={<div>query-result-page</div>} />
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
    window.sessionStorage.clear();
  });

  it("sends browsers to the light portal", async () => {
    mockAuthFetch();
    renderPage();
    await submitLogin();
    await waitFor(() => expect(getToken()).toBe("jwt-abc"));
    expect(await screen.findByText("portal-home")).toBeInTheDocument();
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

  it("restores and saves an anonymous query after login", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/auth/login") return Promise.resolve({ ok: true, status: 200, json: async () => AUTH_OK, text: async () => JSON.stringify(AUTH_OK) } as Response);
      if (url === "/api/cloud/queries") return Promise.resolve({ ok: true, status: 200, json: async () => ({ id: "q1" }) } as Response);
      return Promise.reject(new Error(`unexpected ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.setItem("sigmx_pending_saved_query", JSON.stringify({ query: "低估值 高股息", result_summary: { matches: 2 } }));
    renderPage("/login?next=%2Fquery%2Fsaved");
    await submitLogin();
    expect(await screen.findByText("query-result-page")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("sigmx_pending_saved_query")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith("/api/cloud/queries", expect.objectContaining({ method: "POST" }));
  });
});
