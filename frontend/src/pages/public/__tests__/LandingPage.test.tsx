import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { LandingPage } from "../LandingPage";

function renderWithRouter() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  it("renders the brand headline and three product shapes", () => {
    renderWithRouter();
    expect(screen.getByText(/面向中国 A 股的/)).toBeInTheDocument();
    expect(screen.getByText("Data Hub")).toBeInTheDocument();
    expect(screen.getByText("桌面客户端")).toBeInTheDocument();
    expect(screen.getByText("云端 AI")).toBeInTheDocument();
  });

  it("renders primary CTAs to register and pricing", () => {
    renderWithRouter();
    const registerLinks = screen.getAllByText("免费注册");
    expect(registerLinks.length).toBeGreaterThanOrEqual(1);
    // 查看套餐 appears in the hero CTA and on multiple product cards.
    expect(screen.getAllByText("查看套餐").length).toBeGreaterThanOrEqual(1);
  });

  it("renders all highlight bullets", () => {
    renderWithRouter();
    expect(screen.getByText(/产品分离、平台能力共享/)).toBeInTheDocument();
    expect(screen.getByText(/激活码开通套餐/)).toBeInTheDocument();
    expect(screen.getByText(/Standalone 离线可用/)).toBeInTheDocument();
  });
});
