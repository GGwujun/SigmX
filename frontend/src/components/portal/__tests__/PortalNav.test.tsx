import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PortalNav } from "../PortalNav";

describe("PortalNav", () => {
  it("keeps portal navigation focused on personal destinations", () => {
    render(
      <MemoryRouter initialEntries={["/me"]}>
        <PortalNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "个人中心" })).toHaveAttribute("href", "/me");
    expect(screen.queryByRole("link", { name: "账户中心" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Data Hub" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Desktop" })).not.toBeInTheDocument();
  });

  it("treats account settings as part of the personal center", () => {
    render(
      <MemoryRouter initialEntries={["/account/data-hub"]}>
        <PortalNav />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "个人中心" })).toHaveAttribute("aria-current", "page");
  });
});
