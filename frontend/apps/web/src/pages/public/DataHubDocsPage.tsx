import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  Check,
  ChevronRight,
  CircleDollarSign,
  Copy,
  Database,
  FileText,
  Landmark,
  Play,
  Search,
  ShieldCheck,
} from "lucide-react";
import { getDataHubCatalog, type DataHubEndpoint } from "@/lib/productApi";

const categories = [
  {
    id: "market",
    label: "行情数据",
    description: "股票、指数与基金行情",
    icon: BarChart3,
  },
  {
    id: "finance",
    label: "财务数据",
    description: "财报、指标与估值",
    icon: FileText,
  },
  {
    id: "capital",
    label: "资金流",
    description: "个股与市场资金",
    icon: CircleDollarSign,
  },
  {
    id: "information",
    label: "公告资讯",
    description: "公告、新闻与研报",
    icon: BookOpen,
  },
  {
    id: "macro",
    label: "宏观行业",
    description: "宏观与产业数据",
    icon: Landmark,
  },
] as const;
type CategoryId = (typeof categories)[number]["id"];

const endpointMeta: Record<
  string,
  { name: string; summary: string; category: CategoryId; frequency: string }
> = {
  "stocks.daily": {
    name: "股票日线行情",
    summary: "获取指定股票的历史日线行情和复权因子。",
    category: "market",
    frequency: "交易日 17:00",
  },
  "stocks.moneyflow": {
    name: "个股资金流向",
    summary: "获取个股主力、大单、中单与小单资金净流入。",
    category: "capital",
    frequency: "交易日 18:00",
  },
  "stocks.basic": {
    name: "股票基础信息",
    summary: "获取上市公司代码、名称、行业和上市状态。",
    category: "market",
    frequency: "每日",
  },
  "finance.indicators": {
    name: "财务指标",
    summary: "获取盈利、偿债、成长和运营能力指标。",
    category: "finance",
    frequency: "财报发布后",
  },
  "boards.daily": {
    name: "板块日线行情",
    summary: "按板块代码查询历史行情，或按交易日与板块类型查看板块排行。",
    category: "macro",
    frequency: "交易日盘后",
  },
  "boards.members": {
    name: "板块成分股",
    summary: "获取指定行业或概念板块当前包含的证券。",
    category: "macro",
    frequency: "每日",
  },
};

function inferCategory(item: DataHubEndpoint): CategoryId {
  if (endpointMeta[item.endpoint_code])
    return endpointMeta[item.endpoint_code].category;
  const code = item.endpoint_code.toLowerCase();
  if (/(news|notice|announcement|content|research|report)/.test(code))
    return "information";
  if (/(money|capital|fund_flow|northbound|dragon_tiger|hot_money)/.test(code))
    return "capital";
  if (/(macro|industry|board|sector)/.test(code)) return "macro";
  if (
    /(finance|financial|fundamental|income|balance|cashflow|indicator|valuation)/.test(
      code,
    )
  )
    return "finance";
  const group = item.dataset_group.toLowerCase();
  if (group.includes("capital") || group.includes("money")) return "capital";
  if (group.includes("finance") || group.includes("fundamental"))
    return "finance";
  if (group.includes("news") || group.includes("notice")) return "information";
  if (group.includes("macro") || group.includes("industry")) return "macro";
  return "market";
}

function describeEndpoint(item: DataHubEndpoint) {
  return (
    endpointMeta[item.endpoint_code] ?? {
      name: item.endpoint_code,
      summary: `访问 ${item.dataset_group} 数据集。`,
      category: inferCategory(item),
      frequency: "按数据源更新",
    }
  );
}

export function DataHubDocsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [items, setItems] = useState<DataHubEndpoint[]>([]);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CategoryId>("market");
  const [selectedCode, setSelectedCode] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    void getDataHubCatalog()
      .then((catalog) => {
        setItems(catalog);
        const routeSegments = location.pathname.split("/").filter(Boolean);
        const routeCode = decodeURIComponent(
          routeSegments[routeSegments.length - 1] ?? "",
        );
        const selected =
          catalog.find((item) => item.endpoint_code === routeCode) ??
          catalog[0];
        if (selected) {
          setSelectedCode(selected.endpoint_code);
          setCategory(inferCategory(selected));
        }
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "目录加载失败"),
      );
  }, []);

  const visibleItems = useMemo(
    () =>
      items.filter(
        (item) =>
          inferCategory(item) === category &&
          `${item.endpoint_code} ${describeEndpoint(item).name} ${item.path_pattern}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [category, items, query],
  );
  const selected =
    items.find((item) => item.endpoint_code === selectedCode) ??
    visibleItems[0] ??
    items[0];
  const selectEndpoint = (item: DataHubEndpoint) => {
    setSelectedCode(item.endpoint_code);
    setCategory(inferCategory(item));
    navigate(
      `/docs/data-hub/${inferCategory(item)}/${encodeURIComponent(item.endpoint_code)}`,
    );
  };
  const selectCategory = (next: CategoryId) => {
    setCategory(next);
    const first = items.find((item) => inferCategory(item) === next);
    if (first) selectEndpoint(first);
  };

  return (
    <div className="min-h-[calc(100vh-7rem)] bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white px-4 py-4 lg:px-6">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-teal-600">
              <Database className="h-4 w-4" /> DATA HUB DOCS{" "}
              <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-500">
                v1
              </span>
            </div>
            <h1 className="mt-1 text-xl font-bold">API 接口文档</h1>
          </div>
          <div className="flex flex-1 items-center justify-end gap-3">
            <label className="relative hidden max-w-sm flex-1 md:block">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <span className="sr-only">搜索接口</span>
              <input
                aria-label="搜索接口"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索接口、字段或路径"
                className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none focus:border-teal-400"
              />
            </label>
            <Link
              to="/account/data-hub"
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold"
            >
              控制台
            </Link>
            <Link
              to="/pricing"
              className="rounded-lg bg-teal-500 px-3 py-2 text-xs font-semibold text-white"
            >
              申请权限
            </Link>
          </div>
        </div>
      </header>
      {error && (
        <div
          role="alert"
          className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
        >
          {error}
        </div>
      )}
      <div className="mx-auto grid max-w-[1600px] md:h-[calc(100vh-10.5rem)] md:min-h-[620px] md:grid-cols-[160px_230px_minmax(0,1fr)] md:overflow-hidden xl:grid-cols-[190px_280px_minmax(0,1fr)]">
        <nav
          aria-label="接口分类"
          className="border-r border-slate-200 bg-white p-3 md:overflow-y-auto"
        >
          <div className="px-2 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
            接口分类
          </div>
          {categories.map(({ id, label, description, icon: Icon }) => (
            <button
              key={id}
              type="button"
              aria-pressed={category === id}
              onClick={() => selectCategory(id)}
              className={`mb-1 w-full rounded-lg px-2.5 py-2.5 text-left ${category === id ? "bg-teal-50 text-teal-700" : "text-slate-600 hover:bg-slate-50"}`}
            >
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Icon className="h-4 w-4" />
                {label}
              </div>
              <div className="mt-1 pl-6 text-[10px] text-slate-400">
                {description}
              </div>
            </button>
          ))}
          <div className="mt-5 border-t border-slate-100 px-2 pt-4 text-xs text-slate-500">
            <div className="flex items-center gap-2 font-semibold text-slate-700">
              <ShieldCheck className="h-4 w-4 text-teal-600" />
              认证方式
            </div>
            <p className="mt-2 leading-5">
              Bearer Credential
              <br />
              <code className="text-[10px]">sxd_live_••••••</code>
            </p>
          </div>
        </nav>
        <section
          aria-label="接口列表"
          className="flex min-h-0 flex-col border-r border-slate-200 bg-white"
        >
          <div className="shrink-0 border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-semibold">
              {categories.find((item) => item.id === category)?.label}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              {visibleItems.length} 个接口
            </div>
          </div>
          <div className="divide-y divide-slate-100 md:overflow-y-auto">
            {visibleItems.map((item) => {
              const meta = describeEndpoint(item);
              return (
                <button
                  key={item.endpoint_code}
                  type="button"
                  onClick={() => selectEndpoint(item)}
                  aria-pressed={selected?.endpoint_code === item.endpoint_code}
                  className={`w-full px-4 py-4 text-left ${selected?.endpoint_code === item.endpoint_code ? "border-l-2 border-teal-500 bg-teal-50/60" : "border-l-2 border-transparent hover:bg-slate-50"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{meta.name}</span>
                    <ChevronRight className="h-4 w-4 text-slate-300" />
                  </div>
                  <code className="mt-1 block truncate text-[10px] text-slate-400">
                    {item.endpoint_code}
                  </code>
                  <div className="mt-2 flex items-center gap-2 text-[10px]">
                    <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-bold text-emerald-700">
                      {item.http_method}
                    </span>
                    <span className="text-slate-400">{meta.frequency}</span>
                  </div>
                </button>
              );
            })}
            {visibleItems.length === 0 && (
              <div className="p-5 text-sm text-slate-400">该分类暂无接口</div>
            )}
          </div>
        </section>
        <article
          aria-label="接口详情"
          className="min-w-0 bg-white px-5 py-6 md:overflow-y-auto lg:px-8"
        >
          {selected ? (
            <EndpointDetail
              item={selected}
              copied={copied}
              onCopy={() => {
                void navigator.clipboard?.writeText?.(curlExample(selected));
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1200);
              }}
            />
          ) : (
            <div className="text-sm text-slate-400">正在加载接口目录…</div>
          )}
        </article>
      </div>
    </div>
  );
}

function curlExample(item: DataHubEndpoint) {
  if (item.endpoint_code === "boards.daily")
    return `curl -H "Authorization: Bearer sxd_live_YOUR_KEY" "https://data.sigmx.cn${item.path_pattern}?board_code=BK0001&start=2026-01-01&limit=100"`;
  if (item.endpoint_code === "boards.members")
    return `curl -H "Authorization: Bearer sxd_live_YOUR_KEY" "https://data.sigmx.cn${item.path_pattern}?board_code=BK0001&limit=100"`;
  return `curl -H "Authorization: Bearer sxd_live_YOUR_KEY" \\\n  "https://data.sigmx.cn${item.path_pattern}?symbol=600519.SH&limit=100"`;
}

function requestSpec(item: DataHubEndpoint) {
  if (item.endpoint_code === "boards.daily")
    return {
      rows: [
        ["board_code", "string", "否", "板块代码，例如 BK0001；与交易日排行查询方式二选一"],
        ["trade_date", "date", "否", "交易日期；未传板块代码时用于排行查询"],
        ["board_type", "string", "否", "板块类型，与交易日期配合筛选"],
        ["start", "date", "否", "历史开始日期，仅板块代码查询有效"],
        ["end", "date", "否", "历史结束日期，仅板块代码查询有效"],
        ["limit", "integer", "否", "返回条数，1–2000，默认 100"],
      ],
      fields: [
        ["board_code", "string", "板块代码"],
        ["name", "string", "板块名称"],
        ["board_type", "string", "板块类型"],
        ["trade_date", "date", "交易日期"],
        ["open", "number", "开盘点位"],
        ["close", "number", "收盘点位"],
        ["rise_rate", "number", "涨跌幅"],
        ["turnover_rate", "number", "换手率"],
      ],
    };
  if (item.endpoint_code === "boards.members")
    return {
      rows: [
        ["board_code", "string", "是", "板块代码，例如 BK0001"],
        ["limit", "integer", "否", "返回条数，1–2000，默认 100"],
      ],
      fields: [
        ["board_code", "string", "板块代码"],
        ["symbol", "string", "证券代码"],
        ["name", "string", "证券名称"],
      ],
    };
  const category = inferCategory(item);
  if (category === "macro")
    return {
      rows: [
        ["indicator_code", "string", "是", "宏观或行业指标代码，例如 cn_pmi"],
        ["start_date", "date", "否", "开始日期 YYYY-MM-DD"],
        ["end_date", "date", "否", "结束日期 YYYY-MM-DD"],
        ["limit", "integer", "否", "返回条数，默认 100"],
      ],
      fields: [
        ["period", "string", "统计周期"],
        ["indicator_code", "string", "指标代码"],
        ["value", "number", "指标值"],
        ["source", "string", "数据来源"],
      ],
    };
  if (category === "information")
    return {
      rows: [
        ["keyword", "string", "否", "标题或正文关键词"],
        ["symbols", "string", "否", "关联证券代码，逗号分隔"],
        ["start_date", "date", "否", "开始日期 YYYY-MM-DD"],
        ["limit", "integer", "否", "返回条数，默认 20"],
      ],
      fields: [
        ["published_at", "datetime", "发布时间"],
        ["title", "string", "标题"],
        ["source", "string", "来源"],
        ["source_url", "string", "原文链接"],
      ],
    };
  return {
    rows: [
      ["symbol", "string", "是", "证券代码，例如 600519.SH"],
      ["start_date", "date", "否", "开始日期 YYYY-MM-DD"],
      ["end_date", "date", "否", "结束日期 YYYY-MM-DD"],
      ["limit", "integer", "否", "返回条数，默认 100"],
    ],
    fields: [
      ["trade_date", "date", "交易日期"],
      ["open", "number", "开盘价"],
      ["close", "number", "收盘价"],
      ["volume", "number", "成交量"],
    ],
  };
}

function EndpointDetail({
  item,
  copied,
  onCopy,
}: {
  item: DataHubEndpoint;
  copied: boolean;
  onCopy: () => void;
}) {
  const meta = describeEndpoint(item);
  const spec = requestSpec(item);
  const [debugOpen, setDebugOpen] = useState(false);
  const responseExample = `{\n  "code": 0,\n  "data": [{ "trade_date": "2026-08-21", "close": 1468.00 }],\n  "credits_charged": ${item.base_cost}\n}`;
  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-700">
              {item.http_method}
            </span>
            <code className="text-xs text-slate-500">{item.endpoint_code}</code>
          </div>
          <h2 className="mt-3 text-2xl font-bold">{meta.name}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            {meta.summary}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
            <div className="text-slate-400">Data Credit</div>
            <div className="mt-1 font-semibold">
              基础 {item.base_cost} · 每 {item.unit_size} {item.unit_name}
            </div>
          </div>
          <button
            type="button"
            aria-expanded={debugOpen}
            onClick={() => setDebugOpen((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-teal-500 px-3 py-2 text-xs font-bold text-white"
          >
            <Play className="h-3.5 w-3.5" />
            在线调试
          </button>
        </div>
      </div>
      {debugOpen && (
        <DebugPanel
          key={item.endpoint_code}
          item={item}
          parameterRows={spec.rows}
        />
      )}
      <DocSection title="请求地址">
        <div className="flex overflow-hidden rounded-lg border border-slate-200">
          <span className="bg-emerald-50 px-3 py-3 text-xs font-bold text-emerald-700">
            {item.http_method}
          </span>
          <code className="min-w-0 flex-1 overflow-x-auto px-3 py-3 text-xs">
            https://data.sigmx.cn{item.path_pattern}
          </code>
        </div>
      </DocSection>
      <DocSection title="请求参数">
        <DataTable
          headers={["参数", "类型", "必填", "说明"]}
          rows={spec.rows}
        />
      </DocSection>
      <DocSection title="返回字段">
        <DataTable
          headers={["字段", "类型", "说明"]}
          rows={[
            ...spec.fields,
            ["credits_charged", "integer", "本次消耗 Data Credit"],
          ]}
        />
      </DocSection>
      <DocSection title="请求示例">
        <div className="relative overflow-hidden rounded-lg bg-slate-950 p-4 text-slate-200">
          <button
            type="button"
            onClick={onCopy}
            className="absolute right-3 top-3 inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-1 text-[10px] text-slate-300"
          >
            {copied ? (
              <Check className="h-3 w-3" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
            {copied ? "已复制" : "复制"}
          </button>
          <pre className="overflow-x-auto pr-16 text-xs leading-6">
            <code>{curlExample(item)}</code>
          </pre>
        </div>
      </DocSection>
      <DocSection title="返回示例">
        <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-200">
          <code>{responseExample}</code>
        </pre>
      </DocSection>
    </div>
  );
}

function DebugPanel({
  item,
  parameterRows,
}: {
  item: DataHubEndpoint;
  parameterRows: string[][];
}) {
  const [credential, setCredential] = useState("");
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [result, setResult] = useState<{
    status: number;
    requestId: string;
    credits: string;
    body: string;
  } | null>(null);

  const run = async () => {
    const missingRequired = parameterRows.find(
      ([name, , required]) => required === "是" && !parameters[name]?.trim(),
    );
    if (!credential.trim()) {
      setValidationError("请输入 Data Hub Credential");
      return;
    }
    if (missingRequired) {
      setValidationError(`请填写必填参数 ${missingRequired[0]}`);
      return;
    }
    setRunning(true);
    setValidationError("");
    setResult(null);
    const search = new URLSearchParams();
    parameterRows.forEach(([name]) => {
      const value = parameters[name]?.trim();
      if (value) search.set(name, value);
    });
    try {
      const response = await fetch(
        `${item.path_pattern}${search.size ? `?${search.toString()}` : ""}`,
        {
          method: item.http_method,
          headers: { Authorization: `Bearer ${credential.trim()}` },
        },
      );
      const rawBody = await response.text();
      let body = rawBody;
      try {
        body = JSON.stringify(JSON.parse(rawBody), null, 2);
      } catch {
        /* Preserve non-JSON responses. */
      }
      setResult({
        status: response.status,
        requestId: response.headers.get("X-Request-ID") || "—",
        credits: response.headers.get("X-DataHub-Credits-Charged") || "0",
        body,
      });
    } catch (reason) {
      setValidationError(
        `请求失败：${reason instanceof Error ? reason.message : String(reason)}`,
      );
    } finally {
      setRunning(false);
    }
  };

  return (
    <section
      aria-label="在线调试面板"
      className="mt-5 rounded-xl border border-teal-200 bg-teal-50/40 p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">在线调试</h3>
          <p className="mt-1 text-xs text-slate-500">
            Credential 仅保存在当前页面内存，刷新或离开页面后清除。
          </p>
        </div>
        <code className="rounded bg-white px-2 py-1 text-[11px] text-slate-500">
          {item.http_method} {item.path_pattern}
        </code>
      </div>
      <label className="mt-4 block text-xs font-semibold text-slate-700">
        Credential
        <input
          aria-label="Credential"
          name="data-hub-debug-credential"
          type="password"
          autoComplete="new-password"
          value={credential}
          onChange={(event) => setCredential(event.target.value)}
          placeholder="sxd_live_••••••"
          className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-teal-400"
        />
      </label>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {parameterRows.map(([name, type, required, description]) => (
          <label key={name} className="text-xs font-semibold text-slate-700">
            {name}
            {required === "是" && <span className="ml-1 text-red-500">*</span>}
            <input
              aria-label={`${name} 参数`}
              type={
                type === "date"
                  ? "date"
                  : type === "integer"
                    ? "number"
                    : "text"
              }
              value={parameters[name] ?? ""}
              onChange={(event) =>
                setParameters((current) => ({
                  ...current,
                  [name]: event.target.value,
                }))
              }
              placeholder={description}
              className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal outline-none focus:border-teal-400"
            />
          </label>
        ))}
      </div>
      {validationError && (
        <div
          role="alert"
          className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {validationError}
        </div>
      )}
      <button
        type="button"
        onClick={() => void run()}
        disabled={running}
        className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50"
      >
        <Play className="h-3.5 w-3.5" />
        {running ? "请求中…" : "发送请求"}
      </button>
      {result && (
        <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="grid grid-cols-3 border-b border-slate-200 bg-slate-50 text-xs">
            <div className="p-3">
              <div className="text-slate-400">状态</div>
              <strong
                className={
                  result.status < 400 ? "text-emerald-700" : "text-red-600"
                }
              >
                HTTP {result.status}
              </strong>
            </div>
            <div className="border-l border-slate-200 p-3">
              <div className="text-slate-400">Request ID</div>
              <strong>{result.requestId}</strong>
            </div>
            <div className="border-l border-slate-200 p-3">
              <div className="text-slate-400">本次消耗</div>
              <strong>{result.credits} Data Credit</strong>
            </div>
          </div>
          <pre className="max-h-80 overflow-auto bg-slate-950 p-4 text-xs leading-6 text-slate-200">
            <code>{result.body}</code>
          </pre>
        </div>
      )}
    </section>
  );
}

function DocSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-7">
      <h3 className="mb-3 text-sm font-bold">{title}</h3>
      {children}
    </section>
  );
}
function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[520px] text-left text-xs">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            {headers.map((header) => (
              <th key={header} className="px-3 py-2.5 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell, index) => (
                <td
                  key={`${row[0]}-${index}`}
                  className={`px-3 py-3 ${index === 0 ? "font-mono font-semibold text-teal-700" : "text-slate-600"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
