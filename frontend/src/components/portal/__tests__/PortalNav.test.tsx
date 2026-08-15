import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PortalNav } from "../PortalNav";

describe("PortalNav", () => {
  it("separates cloud assets, account settings, and public products", () => {
    render(
      <MemoryRouter initialEntries={["/me"]}>
        <PortalNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "我的 SigmX" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("link", { name: "账户中心" })).toHaveAttribute("href", "/account");
    expect(screen.getByRole("link", { name: "Data Hub" })).toHaveAttribute("href", "/product/data-hub");
    expect(screen.getByRole("link", { name: "Desktop" })).toHaveAttribute("href", "/product/desktop");
  });
});
