import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AdminLayout } from "../AdminLayout";

describe("AdminLayout", () => {
  it("exposes separate operations modules and renders its outlet", () => {
    render(<MemoryRouter initialEntries={["/admin/users"]}><Routes><Route path="/admin" element={<AdminLayout />}><Route path="users" element={<div>users-body</div>} /></Route></Routes></MemoryRouter>);
    expect(screen.getByRole("link", { name: "总览" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "用户" })).toHaveAttribute("href", "/admin/users");
    expect(screen.getByRole("link", { name: "订单与兑换" })).toHaveAttribute("href", "/admin/orders");
    expect(screen.getByRole("link", { name: "Data Hub" })).toHaveAttribute("href", "/admin/data-hub");
    expect(screen.getByRole("link", { name: "内容运营" })).toHaveAttribute("href", "/admin/content");
    expect(screen.getByText("users-body")).toBeInTheDocument();
  });

  it("uses the brand logo to return to the public home page", () => {
    render(<MemoryRouter initialEntries={["/admin"]}><Routes><Route path="/admin" element={<AdminLayout />} /></Routes></MemoryRouter>);

    expect(screen.getByRole("link", { name: /SigmX 运营后台/ })).toHaveAttribute("href", "/");
  });
});
