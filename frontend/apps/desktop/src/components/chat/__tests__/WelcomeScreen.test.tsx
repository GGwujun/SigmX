import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WelcomeScreen } from "../WelcomeScreen";

describe("WelcomeScreen", () => {
  const onExample = vi.fn();

  beforeEach(() => onExample.mockClear());

  it("renders the title", () => {
    render(<WelcomeScreen onExample={onExample} />);
    expect(screen.getByText("SigmX")).toBeInTheDocument();
  });

  it("renders capability chips", () => {
    render(<WelcomeScreen onExample={onExample} />);
    expect(screen.getByText("77 个金融技能库")).toBeInTheDocument();
    expect(screen.getByText("29 个智能体集群")).toBeInTheDocument();
    expect(screen.getByText("影子账户回测")).toBeInTheDocument();
  });

  it("renders example categories", () => {
    render(<WelcomeScreen onExample={onExample} />);
    expect(screen.getByText("多市场回测")).toBeInTheDocument();
    expect(screen.getByText("研究与分析")).toBeInTheDocument();
    expect(screen.getByText("智能体集群")).toBeInTheDocument();
  });

  it("calls onExample with prompt when an example button is clicked", async () => {
    render(<WelcomeScreen onExample={onExample} />);
    const user = userEvent.setup();
    await user.click(screen.getByText("跨市场组合"));
    expect(onExample).toHaveBeenCalledTimes(1);
    expect(onExample).toHaveBeenCalledWith(
      expect.stringContaining("risk-parity portfolio"),
    );
  });

  it("renders the helper text", () => {
    render(<WelcomeScreen onExample={onExample} />);
    expect(screen.getByText("描述一个交易策略即可开始。")).toBeInTheDocument();
    expect(screen.getByText("试试这些例子：")).toBeInTheDocument();
  });
});
