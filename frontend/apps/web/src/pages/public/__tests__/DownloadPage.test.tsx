import { describe, it, expect, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { DownloadPage } from "../DownloadPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetchOnce(body: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  } as unknown as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DownloadPage />
    </MemoryRouter>,
  );
}

describe("DownloadPage", () => {
  it("renders the stable version from the server catalog", async () => {
    const fetchMock = mockFetchOnce({
      version: "0.2.0",
      notes: "首个公开版本",
      download_url: "https://example.com/sigmx-setup.exe",
    });
    renderPage();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/catalog/releases/stable",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(await screen.findByText("v0.2.0")).toBeInTheDocument();
    expect(screen.getByText("首个公开版本")).toBeInTheDocument();
    expect(screen.getByText("下载 v0.2.0")).toBeInTheDocument();
  });

  it("shows the error state when the catalog is unreachable", async () => {
    mockFetchOnce({ detail: "boom" }, false);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/无法加载版本信息|boom/)).toBeInTheDocument();
    });
  });

  it("shows 'no download link' when download_url is empty", async () => {
    mockFetchOnce({ version: "0.2.0", notes: "", download_url: "" });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("暂无可用下载链接。")).toBeInTheDocument();
    });
  });
});
