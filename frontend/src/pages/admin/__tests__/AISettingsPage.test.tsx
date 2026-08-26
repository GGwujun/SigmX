import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AISettingsPage } from "../AISettingsPage";

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

describe("AISettingsPage", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/settings")) return ok({ provider: "openai", model_name: "gpt-5.2", base_url: "https://api.openai.com/v1", api_key_configured: true, temperature: .2, timeout_seconds: 90, max_retries: 2, reasoning_effort: "high", providers: [{ code: "openai", name: "OpenAI", default_model: "gpt-5.2", default_base_url: "https://api.openai.com/v1", api_key_required: true }] });
    if (url.endsWith("/source-credentials")) return ok({ tushare_token_configured: false, tpdog_token_configured: false });
    if (url.endsWith("/health")) return ok({ configured: false, detail: "AI model strategy is not configured" });
    return ok({ planning_provider: "openai", planning_model: "gpt-5.2", execution_provider: "openai", execution_model: "gpt-5.2", summary_provider: "openai", summary_model: "gpt-5.2", temperature: .2, max_tokens: 8000, timeout_seconds: 90, max_retries: 2 });
  })));

  it("presents one coherent platform model and data-source form", async () => {
    render(<AISettingsPage/>);
    expect((await screen.findAllByText("OpenAI")).length).toBeGreaterThan(0);
    expect(screen.getByText("平台模型")).toBeInTheDocument();
    expect(screen.getByText("生成参数")).toBeInTheDocument();
    expect(screen.getByText("数据源凭据")).toBeInTheDocument();
    expect(screen.queryByText("问题规划")).not.toBeInTheDocument();
    expect(screen.queryByText("智能体执行")).not.toBeInTheDocument();
    expect(screen.queryByText("报告总结")).not.toBeInTheDocument();
    expect(screen.getByLabelText("推理强度")).toHaveValue("high");
  });

  it("applies one administrator-selected model to the whole Web research runtime", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<AISettingsPage/>);
    await screen.findAllByText("OpenAI");
    fireEvent.click(screen.getByRole("button", { name: "保存平台 AI 配置" }));
    const strategyCall = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/settings") && init?.method === "PUT");
    expect(strategyCall).toBeTruthy();
    const payload = JSON.parse(String(strategyCall?.[1]?.body));
    expect(payload).toMatchObject({
      provider: "openai", model_name: "gpt-5.2", reasoning_effort: "high",
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
