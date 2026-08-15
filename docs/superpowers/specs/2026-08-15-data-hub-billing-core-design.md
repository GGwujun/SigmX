# Data Hub 计费内核设计

**日期：** 2026-08-15

**状态：** 已确认采用破坏性切换，待书面规格复核

**范围：** 本规格只实现 Data Hub 商业化第二阶段的第一个可独立子项目：数据积分账本、版本化接口目录和新套餐权益。新 API Key、请求计费中间层、全部路由接入和前端控制台分别进入后续子项目。

## 1. 目标

建立独立于研究积分的 Data Hub 数据积分账本和接口价格目录，为后续“按套餐开放接口、按接口成本扣积分”提供唯一权威来源。

该子项目完成后必须满足：

1. 套餐使用 `datahub.dataset_groups` 和 `datahub.monthly_credits` 表达数据权益；
2. 研究积分与数据积分使用不同的表、余额、批次和流水；
3. Data Hub 每个可售接口在版本化目录中拥有稳定 `endpoint_code`、权限组和价格规则；
4. 数据积分支持发放、查询、预授权、按实际成本结算、释放和幂等重放；
5. 旧 `datahub.daily_quota`、`datahub.basic`、`datahub.featured` 和 `datahub.external_api` 不再出现在新目录种子或新领域接口中；
6. 本子项目暂不把 `/api/v1/*` 请求切换到新账本，避免在新 Key 与完整接口映射尚未实现时产生半套计费链路。

## 2. 非兼容决策

本次不是兼容迁移：

- 不保留旧请求次数计费模型；
- 不为 `usage_daily` 编写到数据积分的迁移器；
- 不把旧 `sx_` API Key 导入新凭证系统；
- 不提供旧权益键到新权益键的运行时适配；
- 后续切换中旧 `sx_` Key 将直接失效，用户需要创建新 Key；
- `usage_daily` 和旧订阅表可在最终切换完成后删除，本子项目不提前删除仍被生产路径读取的表。

## 3. 领域边界

### 3.1 研究积分

现有 `CreditLedger`、`credit_lots`、`credit_ledger` 和 `credit_reservations` 继续只负责 AI 研究任务。本子项目不改变 AlphaForge、基金套利、欢迎积分或旧积分迁移逻辑。

### 3.2 数据积分

新增 `DataCreditLedger`，只负责 Data Hub：

- `grant()`：发放套餐、购买或补偿数据积分批次；
- `balance()`：返回可用和七日内到期数据积分；
- `authorize()`：冻结请求允许消耗的最大数据积分；
- `settle()`：按实际成本结算并退回未使用冻结额；
- `release()`：失败或空结果时释放全部冻结额；
- `list_lots()`、`list_entries()`：提供控制台查询能力。

两种账本不得共用余额或发生隐式兑换。

## 4. 数据模型

`product.db` schema version 从 1 升为 2，新增以下表。

### 4.1 `data_credit_lots`

```sql
CREATE TABLE data_credit_lots (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    amount_total INTEGER NOT NULL CHECK (amount_total > 0),
    amount_remaining INTEGER NOT NULL CHECK (amount_remaining >= 0),
    source TEXT NOT NULL,
    expires_at TEXT,
    idempotency_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_id, idempotency_key)
);
```

第一阶段 `owner_id` 存用户 ID；字段命名保留未来组织账户能力，但本子项目不实现组织。

### 4.2 `data_credit_reservations`

```sql
CREATE TABLE data_credit_reservations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    endpoint_code TEXT NOT NULL,
    amount_authorized INTEGER NOT NULL CHECK (amount_authorized > 0),
    amount_settled INTEGER,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('authorized', 'settled', 'released')),
    created_at TEXT NOT NULL,
    settled_at TEXT,
    UNIQUE(owner_id, idempotency_key)
);
```

### 4.3 `data_credit_allocations`

```sql
CREATE TABLE data_credit_allocations (
    reservation_id TEXT NOT NULL,
    lot_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    PRIMARY KEY (reservation_id, lot_id),
    FOREIGN KEY (reservation_id) REFERENCES data_credit_reservations(id),
    FOREIGN KEY (lot_id) REFERENCES data_credit_lots(id)
);
```

现有研究积分通过流水反查分配，本账本显式保存分配，避免结算部分退款时依赖流水重建。

### 4.4 `data_credit_ledger`

```sql
CREATE TABLE data_credit_ledger (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    lot_id TEXT,
    reservation_id TEXT,
    delta INTEGER NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('grant', 'authorize', 'settle', 'release')),
    idempotency_key TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
```

`authorize` 写负数，`release` 写正数，`settle` 写零并记录实际成本。账本不可变。

### 4.5 `datahub_endpoint_catalog`

```sql
CREATE TABLE datahub_endpoint_catalog (
    endpoint_code TEXT NOT NULL,
    catalog_version INTEGER NOT NULL,
    http_method TEXT NOT NULL,
    path_pattern TEXT NOT NULL,
    dataset_group TEXT NOT NULL,
    pricing_mode TEXT NOT NULL CHECK (pricing_mode IN ('free', 'fixed', 'per_unit')),
    base_cost INTEGER NOT NULL CHECK (base_cost >= 0),
    unit_name TEXT,
    unit_size INTEGER,
    unit_cost INTEGER,
    max_cost INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (endpoint_code, catalog_version),
    UNIQUE (http_method, path_pattern, catalog_version)
);
```

`fixed` 只使用 `base_cost`；`per_unit` 使用 `base_cost + ceil(actual_units / unit_size) * unit_cost`，并受 `max_cost` 限制；`free` 的成本固定为零。

## 5. 数据积分状态机

### 5.1 发放

`grant(owner_id, amount, source, expires_at, idempotency_key)` 创建批次和 `grant` 流水。同一所有者和幂等键重放时返回原批次，不重复发放。

### 5.2 预授权

`authorize(owner_id, endpoint_code, max_cost, idempotency_key)` 在一个 `BEGIN IMMEDIATE` 事务中：

1. 查找同幂等键的预约并直接返回；
2. 按过期时间升序选择未过期批次，永久批次排最后；
3. 余额不足则抛出 `InsufficientDataCredits`，且任何批次不得变化；
4. 从批次余额冻结 `max_cost`；
5. 写入预约、分配和负数流水。

### 5.3 结算

`settle(reservation_id, actual_cost, idempotency_key)` 要求 `0 <= actual_cost <= amount_authorized`：

- `actual_cost == 0` 等价于释放全部冻结额，但预约最终状态仍为 `settled`；
- 多余冻结额按原分配批次恢复；
- 预约记录实际成本和结算时间；
- 再次结算返回第一次结果，不重复恢复积分；
- 已释放预约不能结算；已结算预约不能用不同实际成本覆盖。

### 5.4 释放

`release(reservation_id, idempotency_key)` 将原分配全部恢复并把状态改为 `released`。重复释放无副作用；已结算预约不能释放。

## 6. 接口目录服务

新增 `DataHubEndpointCatalog`：

- `get(endpoint_code, version=None)`：默认返回该接口最新启用版本；
- `match(method, path, version=None)`：精确匹配当前实际路由路径；
- `list(version=None, enabled_only=True)`：用于管理后台与文档；
- `estimate(endpoint, requested_units)`：返回最大预授权成本；
- `calculate(endpoint, actual_units)`：返回实际结算成本。

目录种子覆盖当前 `sigmx_routes.py` 的全部 49 个 `/api/v1/*` GET 路由。`/api/v1/health` 属于 `basic.v1` 且免费。第一版价格使用四档：

- 免费：健康检查、最新交易日；
- 1 分固定：元数据和轻量市场概览；
- 2–5 分固定：标准行情、财务、资金和事件；
- 按 1000 行阶梯：日线、分钟线、逐笔和全市场批量接口。

具体路由、`endpoint_code`、权限组和价格必须作为代码中的完整种子表进入实施计划，不允许用“其余接口类似”省略。

## 7. 新套餐权益

套餐种子删除旧 Data Hub 权益键，增加：

```text
datahub.enabled
datahub.dataset_groups
datahub.monthly_credits
datahub.rate_limit_per_minute
datahub.concurrent_limit
datahub.max_rows_per_request
datahub.history_depth_days
datahub.commercial_use
```

`PlanSeed.entitlements` 从 `dict[str, int | bool]` 扩展为允许字符串列表。首期值：

| 套餐 | 权限组 | 月度数据积分 | 频率/分钟 | 并发 | 单次最大行数 | 历史深度 |
|---|---|---:|---:|---:|---:|---:|
| Free | `basic.v1` | 1,000 | 30 | 1 | 1,000 | 365天 |
| Advanced | `basic.v1`,`market.v1` | 30,000 | 120 | 3 | 10,000 | 5年 |
| Pro | `basic.v1`,`market.v1`,`finance.v1`,`pro.v1` | 150,000 | 600 | 10 | 100,000 | 20年 |
| Enterprise | 合同配置 | 0（合同发放） | 0（合同配置） | 0 | 0 | 0 |

Enterprise 的零值表示必须由合同权益覆盖，不表示无限。后续组织子项目实现合同覆盖；在此之前企业套餐不能通过默认零值调用付费接口。

## 8. 月度发放边界

本子项目提供 `grant_monthly_data_credits(owner_id, plan_code, period)` 领域函数，幂等键固定为 `data-plan-month:{owner_id}:{plan_code}:{YYYY-MM}`，到期时间为下一自然月第一天 UTC。激活和月度续发接入在第四个批次完成；本子项目只提供并测试领域能力，不修改现有 Commerce 激活事务。

## 9. API 边界

本子项目新增只读领域路由：

- `GET /api/data-credits/me`：可用余额、七日内到期量；
- `GET /api/data-credits/lots`：数据积分批次；
- `GET /api/data-credits/ledger`：数据积分流水；
- `GET /api/datahub/catalog`：当前启用接口目录。

不公开预授权、结算和释放 HTTP API；这些只能被后续 Data Hub 计费中间层调用，防止客户端操纵成本。

## 10. 错误与一致性

- `InsufficientDataCredits`：预授权余额不足；
- `UnknownDataCreditReservation`：预约不存在；
- `InvalidDataCreditSettlement`：实际成本越界或状态冲突；
- `UnknownDataHubEndpoint`：接口未登记或未启用；
- `InvalidPricingRule`：目录定价字段组合不合法。

所有写操作使用 `ProductStore.transaction()`；不得在事务外修改批次余额。SQLite 连接继续使用 WAL、外键和进程内写锁。并发测试必须证明两个同时预授权请求不会让余额为负。

## 11. 测试与验收

至少覆盖：

1. 数据积分与研究积分余额完全隔离；
2. 发放幂等；
3. 过期批次不计入余额；
4. 最早到期批次优先冻结；
5. 余额不足不产生部分扣减；
6. 预授权幂等；
7. 固定价格全额结算；
8. 阶梯价格部分结算并退回差额；
9. 空结果零成本结算；
10. 失败释放和重复释放；
11. 已结算与已释放状态冲突；
12. 并发预授权不透支；
13. 49 个现有 Data Hub 路由全部存在目录项；
14. 未登记接口默认失败；
15. 套餐种子不含四个旧权益键；
16. 新只读 API 只返回当前用户数据；
17. 现有研究积分、激活、设备和前端测试不回归；
18. 全量 Python 测试通过。

## 12. 非目标

本子项目不实现新 `sxd_live_` API Key、Scope、IP 白名单、限流、并发控制、Data Hub 请求中间层、响应计费头、旧 Key 删除、前端 Data Hub 控制台或组织账户。上述能力依赖本规格的账本和目录，在后续子项目连续实现。
