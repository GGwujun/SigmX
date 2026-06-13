import { render, screen } from "@testing-library/react";
import { AgentAvatar } from "../AgentAvatar";

describe("AgentAvatar", () => {
  it("renders the letter P", () => {
    render(<AgentAvatar />);
    expect(screen.getByText("P")).toBeInTheDocument();
  });

  it("uses theme primary styling", () => {
    const { container } = render(<AgentAvatar />);
    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain("bg-primary/10");
    expect(el.className).toContain("text-primary");
  });
});
