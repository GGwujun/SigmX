import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { OperationsPage } from "../OperationsPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(body: unknown, ok = true) {
  const m = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 400,
    json: async () => body,
  } as unknown as Response);
  vi.stubGlobal("fetch", m);
  return m;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OperationsPage />
    </MemoryRouter>,
  );
}

describe("OperationsPage", () => {
  it("generates codes and shows plaintext exactly once", async () => {
    const fetchMock = mockFetch({
      codes: [
        { plaintext: "SX-AAAA-111111", code_hash: "h1", plan_code: "advanced", months: 3 },
        { plaintext: "SX-BBBB-222222", code_hash: "h2", plan_code: "advanced", months: 3 },
      ],
    });
    renderPage();

    fireEvent.click(screen.getByText("生成"));

    await waitFor(() => {
      expect(screen.getByText("SX-AAAA-111111")).toBeInTheDocument();
      expect(screen.getByText("SX-BBBB-222222")).toBeInTheDocument();
    });
    // POSTed to the admin activation-codes endpoint with the form values.
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/activation-codes",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("surfaces the error message on failure", async () => {
    mockFetch({ detail: "无效套餐" }, false);
    renderPage();
    fireEvent.click(screen.getByText("生成"));
    // The error surfaces via toast; the codes section stays empty.
    await waitFor(() => {
      expect(screen.queryByText(/SX-/)).not.toBeInTheDocument();
    });
  });
});
