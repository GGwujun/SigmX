import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AccountNav } from "../AccountNav";

describe("AccountNav", () => {
  it("separates the product home from commercial and security settings", () => {
    render(
      <MemoryRouter initialEntries={["/account"]}>
        <AccountNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "概览" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("link", { name: "账户与安全" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("link", { name: "套餐与权益" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data Hub" })).toHaveAttribute("href", "/account/data-hub");
    expect(screen.queryByRole("link", { name: "AI 研究额度" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "设备授权" })).not.toBeInTheDocument();
  });
});
