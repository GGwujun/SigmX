import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { DesktopOnly } from "../../router";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<DesktopOnly />}>
          <Route path="/app" element={<div>workbench</div>} />
        </Route>
        <Route path="/portal" element={<div>portal-redirect-target</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DesktopOnly guard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects browsers to /portal", () => {
    renderAt("/app");
    expect(screen.queryByText("workbench")).not.toBeInTheDocument();
    expect(screen.getByText("portal-redirect-target")).toBeInTheDocument();
  });

  it("lets the desktop client through to the workbench", () => {
    vi.stubGlobal("sigmxDesktop", { isDesktop: true });
    renderAt("/app");
    expect(screen.getByText("workbench")).toBeInTheDocument();
  });
});
