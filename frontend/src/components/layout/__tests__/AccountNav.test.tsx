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

    expect(screen.getByRole("link", { name: "返回我的 SigmX" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("link", { name: "账户与安全" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("link", { name: "套餐与激活" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data Hub 用量" })).toBeInTheDocument();
  });
});
