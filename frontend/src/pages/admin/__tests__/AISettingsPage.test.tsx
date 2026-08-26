import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AISettingsPage } from "../AISettingsPage";

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

describe("AISettingsPage", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/providers")) return ok([{ code: "openai", name: "OpenAI", base_url: "https://api.openai.com/v1", models: ["gpt-5.2"], enabled: true, configured: true, api_key_masked: "sk-***" }]);
    if (url.endsWith("/sources")) return ok([{ code: "data_hub", enabled: true, priority: 0, markets: ["A股"] }]);
    return ok({ planning_provider: "openai", planning_model: "gpt-5.2", execution_provider: "openai", execution_model: "gpt-5.2", summary_provider: "openai", summary_model: "gpt-5.2", temperature: .2, max_tokens: 8000, timeout_seconds: 90, max_retries: 2 });
  })));

  it("separates model connections, strategy, and source routing", async () => {
    render(<AISettingsPage/>);
    expect((await screen.findAllByText("OpenAI")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /模型策略与生成参数/ }));
    expect(screen.getByText("问题规划")).toBeInTheDocument();
    expect(screen.getByText("智能体执行")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /数据源路由/ }));
    expect(screen.getByText("SigmX Data Hub")).toBeInTheDocument();
    expect(screen.getByText("本地市场库")).toBeInTheDocument();
  });

  it("leaves loading state and shows an actionable error when an API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "登录已过期" }), { status: 401 }))));
    render(<AISettingsPage/>);
    expect(await screen.findByText("登录已过期")).toBeInTheDocument();
    expect(screen.queryByText("正在加载平台配置…")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
  });
});
