# Data Hub First AI 投研技能运行时设计

**日期：** 2026-08-25

**状态：** 待书面规格复核

## 1. 目标

一次性把当前发布的 102 个 AI 投研 Skill 从“各自描述或直连第三方数据源”升级为统一的 SigmX 数据运行协议：适用场景默认调用 Data Hub，许可明确的免费数据源只作为声明式降级路径，无法取得可靠数据时明确失败。技能库必须如实展示来源、认证、可执行性和官方归属。

完成后：

1. 所有 102 个 `SKILL.md` 都包含机器可读的 SigmX 数据策略；
2. Data Hub 支持的 A 股、基金、ETF、指数、资金流、财务和行情能力默认使用 `SIGMX_DATA_HUB_BASE_URL` 与 `SIGMX_DATA_HUB_KEY`；
3. 第三方免费源只能在清单允许时降级，并在结果中保留来源、时间与降级原因；
4. 问财导入 Skill 不再默认请求问财或索取 `IWENCAI_API_KEY`；
5. 数据能力不完整时不得放宽用户条件、虚构指标或生成伪结果；
6. 技能广场不再把所有内容标记为 SigmX 官方。

## 2. 范围与非目标

本批次覆盖统一 Python 客户端、数据路由、Skill 清单迁移、公开目录 API、技能广场和详情页、安装提示、审计工具及测试。保留稳定 slug，避免已安装 Skill 失效。

本批次不新增社区上传、评分、作者结算，不抓取新的第三方 Skill，不改变 Data Credit 计费公式，不承诺 Data Hub 当前没有的数据。Data Hub 新增搜索类数据集不在本批次范围；新闻、公告和研报搜索在缺少等价 Data Hub 接口时使用明确声明的候补源或返回能力缺失。

## 3. 方案选择

采用“统一运行时 + 声明式清单”，不在 102 个 Skill 中复制 HTTP、认证、分页、重试和降级代码。

- 方案 A：逐个改 URL。改动快，但认证、字段和错误处理会持续分叉，拒绝采用。
- 方案 B：统一运行时和清单。初始改动较大，但可测试、可审计、可持续扩展，采用。
- 方案 C：Data Hub 代理所有第三方请求。会把外部授权、许可和稳定性风险搬进服务端，本批次不采用。

## 4. 统一数据策略模型

每个 Skill 在 front matter 中增加：

```yaml
sigmx:
  ownership: official | adapted | third_party | community
  execution: executable | instructional
  primary_source: data_hub | public_source | user_source | none
  datahub_endpoints:
    - stocks.daily
    - stocks.daily_basic
  fallback_sources:
    - akshare
  markets:
    - CN_A
  credentials:
    - SIGMX_DATA_HUB_KEY
```

约束：

- `primary_source=data_hub` 时 `datahub_endpoints` 至少包含一个当前目录中的 endpoint code；
- `fallback_sources` 只能来自受控注册表，不允许任意 URL；
- `execution=executable` 必须存在脚本入口或引用统一运行时的标准命令；
- `ownership=official` 只用于由 SigmX 维护且默认依赖 Data Hub 的内容；
- 原问财内容迁移为 `adapted`，许可证文件保留，页面不显示为 SigmX 原创；
- 纯方法论 Skill 可为 `instructional`，但必须声明执行时需要的数据能力。

## 5. 统一运行时

新增 `src/skill_runtime`：

- `models.py`：数据请求、来源、溯源、降级和错误类型；
- `registry.py`：Data Hub endpoint 与免费源能力注册表；
- `client.py`：Data Hub Bearer 认证、超时、分页、稳定错误映射；
- `router.py`：按清单选择主源和候补源；
- `cli.py`：供本地 AI 智能体及 Skill 脚本调用的统一命令；
- `manifest.py`：解析、校验和序列化 `sigmx` front matter。

统一请求数据结构：

```python
DataRequest(
    capability="equity.daily",
    params={"codes": ["000001.SZ"], "start": "2026-01-01"},
    allow_fallback=True,
)
```

统一响应必须包含：

```python
DataResult(
    rows=[...],
    source="sigmx_data_hub",
    endpoint_code="stocks.daily",
    as_of="2026-08-25",
    degraded=False,
    degradation_reason=None,
)
```

## 6. 路由与降级规则

执行顺序固定为：

```text
解析 Skill 清单
→ 验证请求能力与参数
→ 尝试 Data Hub
→ 仅在认证缺失、网络不可达或能力未覆盖时考虑清单候补源
→ 校验候补结果字段和时间
→ 返回带溯源的结果，或返回稳定能力错误
```

不允许降级的情况：

- Data Hub 返回权限拒绝、积分不足或参数错误；
- 候补源不能提供同一口径；
- 用户明确要求只使用 Data Hub；
- 点时数据、复权口径或历史财务披露时点无法保持一致。

免费源优先级：A 股基础行情 `akshare` 后接 `mootdx`；海外股票 `yfinance`；数字资产 `okx` 后接 `ccxt`；美国监管文件 `sec`。Tushare 是用户自备源，不归类为免费匿名候补。

## 7. 102 个 Skill 的迁移分组

### 7.1 Data Hub 主源

A 股行情、基本面、财务报表、估值、股息、资金流、板块、ETF、基金、指数、期权、龙虎榜、技术分析、因子和回测类 Skill，映射到当前 49 个 endpoint code。方法类 Skill 通过统一运行时获取输入数据，不再直接调用 Tushare、AKShare 或问财。

### 7.2 免费或用户源主导

数字资产、链上、DeFi、美国监管文件、全球宏观、海外 ETF 等 Data Hub 未覆盖能力，声明 `public_source` 或 `user_source`。这类内容可以发布，但不得展示“Data Hub 主源”。

### 7.3 原问财 Skill

22 个 `hithink-*` 及公告、新闻、研报搜索保留 slug。可由 Data Hub 等价覆盖的查询改写为统一 capability 调用；自然语言全市场查询拆成结构化条件后再调用 Data Hub。无法等价覆盖的全文检索能力标记为 `adapted` 和 `partial`，不得继续默认请求 `openapi.iwencai.com`。原始许可证和来源声明保留。

## 8. 公开目录与 Web 展示

公开 Skill API 返回：

- `ownership` 与中文标签；
- `execution`；
- `primary_source`；
- `datahub_endpoints`；
- `fallback_sources`；
- `markets`；
- `credential_required`；
- `capability_status=full | partial | instructional`。

技能卡片显示归属、主数据源和可执行状态。详情页显示 Data Hub 接口、候补源、降级规则、认证要求和风险。安装 Prompt 只要求清单实际需要的环境变量；不再对所有 Skill 一律要求 Data Hub Credential。

## 9. 安全、许可与隐私

- 密钥只能从环境变量读取，不写入 Skill、日志、命令参数或结果；
- 统一客户端不得把 SigmX Credential 发送到非 SigmX 域名；
- 第三方许可证、来源和用途限制保留；
- 候补源响应不得冒充 Data Hub 数据；
- 日志只记录 endpoint code、状态、耗时和降级原因，不记录完整 Authorization；
- 旧示例中出现的真实第三方 Key 必须从仓库和生成安装文案中清除。

## 10. 错误契约

稳定错误包括：

- `credential_missing`
- `credential_invalid`
- `capability_not_supported`
- `fallback_not_allowed`
- `fallback_schema_mismatch`
- `source_unavailable`
- `data_stale`
- `manifest_invalid`

Skill 必须把错误解释为用户可行动的信息，不得把错误转换成空候选或静默切换口径。

## 11. 自动审计与完成标准

新增全目录审计，完成必须同时满足：

1. 102/102 个 `SKILL.md` 通过 schema 校验；
2. 0 个 Skill 默认引用 `openapi.iwencai.com`；
3. 0 个 Data Hub 主源 Skill 直接读取 `IWENCAI_API_KEY`、`TUSHARE_TOKEN`；
4. 所有 `datahub_endpoints` 都存在于当前目录；
5. 所有可执行 Skill 均存在可调用入口；
6. 所有候补源都在受控注册表；
7. 所有目录项的归属和数据源标签与清单一致；
8. Data Hub 客户端、路由、错误和降级行为有单元测试；
9. 公开 API、广场、详情页和安装文案有前端及后端测试；
10. 完整后端测试、前端测试、TypeScript 检查和生产构建通过。

## 12. 发布与兼容

保持 `/skills/:slug`、`sigmx skills install <slug>` 和现有 slug 不变。清单 schema 版本设为 `1`。迁移脚本必须幂等，可重复执行且不改写 Skill 正文分析方法。上线时统一替换全部清单与目录 API，不保留混合展示状态。
