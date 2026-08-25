export type DataSet = { id: string; name: string; category: string; cadence: string; freshness: string; coverage: string; quality: string; sla: string; endpoint: string; consumers: string[] };

export const dataCategories = ["全部数据", "市场数据", "公司财报", "资金流向", "估值数据", "衍生品数据", "行业数据", "事件数据"];

export const dataSets: DataSet[] = [
  { id: "snapshot", name: "A 股实时行情快照", category: "市场数据", cadence: "实时", freshness: "1 分钟前", coverage: "99.8%", quality: "99.3%", sla: "99.9%", endpoint: "/v1/market/equity-cn/snapshot", consumers: ["市场发现", "公司研究"] },
  { id: "daily", name: "A 股日行情", category: "市场数据", cadence: "日更", freshness: "2026-08-23 08:10", coverage: "100%", quality: "99.1%", sla: "99.5%", endpoint: "/v1/market/equity-cn/daily", consumers: ["公司研究", "策略回测", "组合管理"] },
  { id: "financial", name: "上市公司核心财务指标", category: "公司财报", cadence: "公告后", freshness: "12 分钟前", coverage: "98.9%", quality: "99.6%", sla: "99.5%", endpoint: "/v1/fundamental/equity-cn/metrics", consumers: ["AI 发现", "公司研究"] },
  { id: "flow", name: "A 股资金流向", category: "资金流向", cadence: "盘中", freshness: "2 分钟前", coverage: "99.2%", quality: "98.8%", sla: "99.0%", endpoint: "/v1/flow/equity-cn/intraday", consumers: ["情报搜索", "市场发现"] },
  { id: "events", name: "公司公告与事件", category: "事件数据", cadence: "实时", freshness: "刚刚", coverage: "99.7%", quality: "99.4%", sla: "99.9%", endpoint: "/v1/events/equity-cn/disclosures", consumers: ["情报搜索", "公司研究"] },
];
