import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AISettingsPage } from "../AISettingsPage";

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

describe("AISettingsPage", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/providers")) return ok([{ code: "openai", name: "OpenAI", base_url: "https://api.openai.com/v1", models: ["gpt-5.2"], enabled: true, configured: true, api_key_masked: "sk-***" }]);
    if (url.endsWith("/sources")) return ok([{ code: "data_hub", enabled: true, priority: 0, markets: ["A股"] }]);
    if (url.endsWith("/health")) return ok({ configured: false, detail: "AI model strategy is not configured" });
    return ok({ planning_provider: "openai", planning_model: "gpt-5.2", execution_provider: "openai", execution_model: "gpt-5.2", summary_provider: "openai", summary_model: "gpt-5.2", temperature: .2, max_tokens: 8000, timeout_seconds: 90, max_retries: 2 });
  })));

  it("presents the same four administrator tasks as the established client settings", async () => {
    render(<AISettingsPage/>);
    expect((await screen.findAllByText("OpenAI")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /模型配置/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /生成参数/ }));
    expect(screen.getByText("智能体默认模型")).toBeInTheDocument();
    expect(screen.queryByText("问题规划")).not.toBeInTheDocument();
    expect(screen.queryByText("智能体执行")).not.toBeInTheDocument();
    expect(screen.queryByText("报告总结")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /数据源配置/ }));
    expect(screen.getByText("SigmX Data Hub")).toBeInTheDocument();
    expect(screen.getByText("本地市场库")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /运行检查/ }));
    expect(screen.getByText("平台 AI 运行状态")).toBeInTheDocument();
    expect(screen.getByText("尚未配置默认模型，请先在“生成参数”中保存模型。")).toBeInTheDocument();
  });

  it("applies one administrator-selected model to the whole Web research runtime", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<AISettingsPage/>);
    await screen.findAllByText("OpenAI");
    fireEvent.click(screen.getByRole("button", { name: /生成参数/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存生成参数" }));
    const strategyCall = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/strategy") && init?.method === "PUT");
    expect(strategyCall).toBeTruthy();
    const payload = JSON.parse(String(strategyCall?.[1]?.body));
    expect(payload).toMatchObject({
      planning_provider: "openai", planning_model: "gpt-5.2",
      execution_provider: "openai", execution_model: "gpt-5.2",
      summary_provider: "openai", summary_model: "gpt-5.2",
    });
  });

  it("leaves loading state and shows an actionable error when an API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: "登录已过期" }), { status: 401 }))));
    render(<AISettingsPage/>);
    expect(await screen.findByText("登录已过期")).toBeInTheDocument();
    expect(screen.queryByText("正在加载平台配置…")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
  });
});
