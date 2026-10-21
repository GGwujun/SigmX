import { fireEvent, render, screen } from "@testing-library/react";

import { PublishReportSnapshot } from "../PublishReportSnapshot";

const cloudApi = vi.hoisted(() => ({ publishReport: vi.fn() }));
vi.mock("@/lib/cloudResearchApi", () => ({ cloudResearchApi: cloudApi }));

describe("PublishReportSnapshot", () => {
  it("publishes only the explicitly reviewed title and redacted summary", async () => {
    cloudApi.publishReport.mockResolvedValue({ id: "r1", slug: "public-1", title: "标题", summary: "脱敏摘要", created_at: "now", revoked_at: null });
    render(<PublishReportSnapshot suggestedTitle="贵州茅台研究" />);
    fireEvent.click(screen.getByRole("button", { name: "发布 Web 快照" }));
    expect(screen.getByText(/不会上传完整报告/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("公开标题"), { target: { value: "标题" } });
    fireEvent.change(screen.getByLabelText("脱敏摘要"), { target: { value: "脱敏摘要" } });
    fireEvent.click(screen.getByRole("button", { name: "确认发布脱敏快照" }));
    expect(await screen.findByRole("link", { name: "打开公开快照" })).toHaveAttribute("href", "/research/public-1");
    expect(cloudApi.publishReport).toHaveBeenCalledWith("标题", "脱敏摘要");
  });
});
