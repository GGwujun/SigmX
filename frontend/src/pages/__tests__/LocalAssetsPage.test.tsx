import { render, screen, waitFor } from "@testing-library/react";
import { LocalAssetsPage } from "../LocalAssetsPage";

vi.mock("@/lib/harnessApi", () => ({
  getHarnessAssets: vi.fn().mockResolvedValue({
    summary: { counts: { dataset: 1, report: 1, cache: 1 }, total_size_bytes: 1048576, latest_modified_at: "2026-08-16T03:00:00Z" },
    items: [{ id: "report:quality.md", kind: "report", name: "quality.md", extension: "md", size_bytes: 2048, modified_at: "2026-08-16T03:00:00Z", version: "20260815", local_only: true }],
  }),
}));

it("renders categorized local assets and their data version", async () => {
  render(<LocalAssetsPage />);
  expect(screen.getByRole("heading", { name: "本地资产" })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("quality.md")).toBeInTheDocument());
  expect(screen.getByText("版本 20260815")).toBeInTheDocument();
  expect(screen.getByText(/仅本机可见/)).toBeInTheDocument();
});
