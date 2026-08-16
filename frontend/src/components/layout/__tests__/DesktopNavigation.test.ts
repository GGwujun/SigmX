import { DESKTOP_PRIMARY_NAV } from "../Layout";

it("exposes the seven Financial Harness work areas as primary navigation", () => {
  expect(DESKTOP_PRIMARY_NAV.map(item => [item.to, item.label])).toEqual([
    ["/app", "工作台"], ["/research", "研究中心"], ["/market", "市场工作台"],
    ["/quant", "量化实验室"], ["/tracking", "跟踪中心"], ["/runs", "运行中心"],
    ["/assets", "本地资产"],
  ]);
});
