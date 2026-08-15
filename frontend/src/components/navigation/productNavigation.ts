export interface ProductNavigationItem {
  to: string;
  label: string;
  description: string;
}

export const PUBLIC_PRODUCT_LINKS = [
  { to: "/product/desktop", label: "Desktop", description: "Financial Harness 专业工作台" },
  { to: "/product/data-hub", label: "Data Hub", description: "金融数据 API 与云数据" },
  { to: "/pricing", label: "套餐", description: "产品授权与用量额度" },
  { to: "/download", label: "下载", description: "获取 SigmX Desktop" },
] as const satisfies readonly ProductNavigationItem[];
