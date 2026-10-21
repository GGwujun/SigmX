import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AccountPage } from "../AccountPage";

describe("AccountPage", () => {
  it("gives every account screen the same workspace width and sub-navigation", () => {
    render(<MemoryRouter><AccountPage><h1>账户内容</h1></AccountPage></MemoryRouter>);
    expect(screen.getByRole("main", { name: "账户页面" })).toHaveClass("max-w-6xl");
    expect(screen.getByRole("link", { name: "账户与安全" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "账户内容" })).toBeInTheDocument();
  });
});
