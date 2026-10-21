import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DesktopProductPage } from "../DesktopProductPage";

describe("DesktopProductPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tag_name: "v0.1.7", assets: [
        { name: "SigmX-Setup-0.1.7.exe", browser_download_url: "https://github.com/GGwujun/SigmX/releases/download/v0.1.7/SigmX-Setup-0.1.7.exe" },
        { name: "SigmX-0.1.7-mac-arm64.dmg", browser_download_url: "https://github.com/GGwujun/SigmX/releases/download/v0.1.7/SigmX-0.1.7-mac-arm64.dmg" },
      ] }),
    }));
  });

  it("positions Desktop as a local-first continuous research workbench", async () => {
    render(<MemoryRouter><DesktopProductPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: /本地优先的专业投研工作台/ })).toBeInTheDocument();
    expect(screen.getByText("私有数据不出设备")).toBeInTheDocument();
    expect(screen.getByText("持续运行的研究任务")).toBeInTheDocument();
    expect(await screen.findAllByRole("link", { name: /下载 Windows 版/ })).toSatisfy((links: HTMLElement[]) => links.every((link) => link.getAttribute("href")?.endsWith("SigmX-Setup-0.1.7.exe")));
    expect(screen.getAllByRole("link", { name: /下载 Mac 版/ })[0]).toHaveAttribute("href", "https://github.com/GGwujun/SigmX/releases/download/v0.1.7/SigmX-0.1.7-mac-arm64.dmg");
    expect(fetch).toHaveBeenCalledWith("https://api.github.com/repos/GGwujun/SigmX/releases/latest", expect.any(Object));
  });

  it("shows the end-to-end Desktop workflow and product boundaries", () => {
    render(<MemoryRouter><DesktopProductPage /></MemoryRouter>);
    expect(screen.getByText("Web 发现机会")).toBeInTheDocument();
    expect(screen.getByText("Desktop 深入验证")).toBeInTheDocument();
    expect(screen.getByText("建立持续跟踪")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "产品能力边界" })).toBeInTheDocument();
  });

  it("switches between standalone and connected mode explanations", () => {
    render(<MemoryRouter><DesktopProductPage /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Connected" }));
    expect(screen.getByRole("button", { name: "Connected" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: /连接 Data Hub/ })).toBeInTheDocument();
    expect(screen.getByText("跨设备同步研究配置")).toBeInTheDocument();
  });

  it("does not claim current macOS support before a Mac release asset exists", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ tag_name: "v0.1.7", assets: [
      { name: "SigmX-Setup-0.1.7.exe", browser_download_url: "https://github.com/GGwujun/SigmX/releases/download/v0.1.7/SigmX-Setup-0.1.7.exe" },
    ] }) }));
    render(<MemoryRouter><DesktopProductPage /></MemoryRouter>);
    expect(await screen.findByText(/Mac 版正在构建/)).toBeInTheDocument();
    expect(screen.queryByText(/macOS 12\+/)).not.toBeInTheDocument();
  });
});
