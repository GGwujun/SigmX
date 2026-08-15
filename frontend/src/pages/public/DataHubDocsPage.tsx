import { useEffect, useState, type ReactNode } from "react";

import { getDataHubCatalog, type DataHubEndpoint } from "@/lib/productApi";

export function DataHubDocsPage() {
  const [items, setItems] = useState<DataHubEndpoint[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    void getDataHubCatalog().then(setItems).catch((reason) =>
      setError(reason instanceof Error ? reason.message : "目录加载失败"));
  }, []);
  return (
    <div className="mx-auto max-w-6xl space-y-10 px-4 py-12">
      <header>
        <p className="text-xs font-medium uppercase tracking-widest text-primary">SigmX Data Hub Docs</p>
        <h1 className="mt-2 text-3xl font-bold">个人开发者数据接口</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
          使用个人 `sxd_live_` Credential，通过套餐接口组授权并按 Data Credit 计量。所有价格与权限来自版本化服务端目录。
        </p>
      </header>
      <section className="grid gap-4 lg:grid-cols-3">
        <Example title="cURL">{`curl -H "Authorization: Bearer sxd_live_YOUR_KEY" \\
  "https://data.sigmx.cn/api/v1/stocks/daily?symbol=600519.SH&limit=100"`}</Example>
        <Example title="Python SDK 示例">{`import os
from sigmx_datahub import DataHubClient

client = DataHubClient(os.environ["SIGMX_DATAHUB_KEY"])
result = client.stocks_daily("600519.SH", limit=100)
print(result.data)
print(result.credits_charged)`}</Example>
        <Example title="CLI">{`pip install sigmx-datahub
export SIGMX_DATAHUB_KEY=sxd_live_...
sigmx-data get /api/v1/stocks/daily \\
  --param symbol=600519.SH --param limit=100`}</Example>
      </section>
      <section>
        <h2 className="text-xl font-semibold">接口目录</h2>
        {error && <p role="alert" className="mt-3 text-destructive">{error}</p>}
        <div className="mt-4 overflow-hidden rounded-xl border">
          <div className="grid grid-cols-[1fr_90px_120px] gap-3 border-b bg-muted/40 px-4 py-3 text-xs font-medium"><span>接口</span><span>方法</span><span>计费</span></div>
          {items.map((item) => <div key={item.endpoint_code} className="grid grid-cols-[1fr_90px_120px] gap-3 border-b px-4 py-3 text-sm last:border-b-0"><div><code>{item.endpoint_code}</code><div className="mt-1 text-xs text-muted-foreground">{item.path_pattern}</div></div><span>{item.http_method}</span><span>{item.pricing_mode} · {item.base_cost}</span></div>)}
        </div>
      </section>
    </div>
  );
}

function Example({ title, children }: { title: string; children: ReactNode }) {
  return <div className="rounded-xl border bg-card p-5"><h2 className="mb-4 font-semibold">{title}</h2><pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs"><code className="whitespace-pre-wrap">{children}</code></pre></div>;
}
