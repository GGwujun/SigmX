# 个人 Data Hub Credential 与统一计费网关设计

**日期：** 2026-08-15

**状态：** 待书面规格复核

**范围：** 彻底替换旧 `sx_` API Key、每日请求配额和旧订阅入口，为个人用户实现新 `sxd_live_` Credential、套餐授权、请求限流、并发控制、Data Credit 计费闭环及 Web 个人控制台。

## 1. 目标

本阶段完成 Data Hub 从“按日请求次数授权”到“按套餐开放数据集、按接口成本扣 Data Credit”的破坏性切换。完成后：

1. Data Hub 只接受个人用户创建的 `sxd_live_` Credential；
2. 当前 49 个 `/api/v1/*` GET 接口全部经过同一个失败关闭的授权与计费网关；
3. 套餐的数据集组、频率、并发、单次行数、历史深度和积分余额均在查询前验证；
4. 请求先冻结最大成本，成功后按实际返回量结算，失败时释放；
5. Web 个人中心可以管理 Key、查看余额、批次、流水和接口调用统计；
6. 旧 `sx_` Key、`api_key` 查询参数、`usage_daily` 请求配额和旧订阅管理入口从产品路径删除。

## 2. 明确边界

系统只实现个人用户，不实现企业、组织、成员、角色、共享额度或合同覆盖。所有 Credential、套餐权益、Data Credit、限流桶、并发租约和调用统计直接绑定 `user_id`。

`enterprise` 套餐可继续出现在营销目录中，但在本技术闭环中不可激活或调用 Data Hub；默认零限制不表示无限。

Desktop Device Token 只用于 Desktop 身份和设备授权，不可作为第三方 Data Hub API Credential。研究积分与 Data Credit 继续完全隔离。

## 3. Credential 模型

新增 `datahub_credentials`：

```sql
CREATE TABLE datahub_credentials (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    ip_allowlist_json TEXT NOT NULL,
    expires_at TEXT,
    last_used_at TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
```

- 明文格式为 `sxd_live_` 加 48 个十六进制字符；
- 只在创建或轮换响应中显示一次；
- 数据库只保存 SHA-256 和用于展示的前缀；
- `scopes_json` 保存允许的 `endpoint_code` 或通配数据集组，最终权限取 Credential Scope 与套餐数据集组的交集；
- 空 IP 白名单表示不限制；非空时只接受精确 IP 或 CIDR；
- 吊销立即生效；轮换等价于创建新 Key 并在同一事务中吊销旧 Key；
- 每个用户最多 10 个未吊销 Credential。

只接受：

```http
Authorization: Bearer sxd_live_<secret>
```

不接受 `X-API-Key`、查询参数 `api_key`、Cookie 或 Desktop Token。

## 4. 统一请求网关

为 `sigmx_routes` 使用自定义 `APIRoute`，在路由业务函数外统一执行：

```text
匹配版本化接口目录
→ Credential 验证
→ 用户当前套餐
→ Credential Scope
→ 套餐 dataset_group
→ IP 白名单
→ 每分钟限流
→ 并发租约
→ 请求行数和历史深度限制
→ Data Credit 最大成本预授权
→ 执行业务处理器
→ 统计实际返回记录数
→ 实际成本结算或失败释放
→ 写调用统计和响应头
```

目录中不存在、被禁用或出现重复映射的 `/api/v1/*` 路由一律失败关闭。免费接口仍要求有效 Credential 和套餐数据集权限，但不冻结积分。

## 5. 套餐授权

网关读取用户实时权益快照中的：

- `datahub.enabled`
- `datahub.dataset_groups`
- `datahub.rate_limit_per_minute`
- `datahub.concurrent_limit`
- `datahub.max_rows_per_request`
- `datahub.history_depth_days`

用户无有效付费权益时使用 Free 套餐。`dataset_group` 不在套餐列表返回 403；行数或历史范围超过限制返回 422；积分不足返回 402；限流返回 429；并发满返回 429。

本阶段把套餐月度 Data Credit 发放接入激活闭环：用户首次使用 Data Hub 时幂等发放当月 Free 积分；激活 Advanced 或 Pro 时幂等发放当月对应积分。Enterprise 不自动发放。

## 6. 限流与并发

新增两张运行时状态表：

```sql
CREATE TABLE datahub_rate_buckets (
    user_id TEXT NOT NULL,
    minute TEXT NOT NULL,
    consumed INTEGER NOT NULL,
    PRIMARY KEY (user_id, minute)
);

CREATE TABLE datahub_concurrency_leases (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

分钟桶和租约均在 `BEGIN IMMEDIATE` 事务中更新。并发检查前删除已过期租约；正常完成或异常退出均主动释放，最长 120 秒自动过期。套餐限制按用户生效，因此同一用户的多个 Key 共用总限额；租约同时记录 Credential ID 用于审计。

## 7. 请求限制解析

网关为目录条目附带请求策略：

- `limit`、`page_size`、`count` 等参数统一归一为 `requested_rows`；
- 未提供时使用接口默认值；
- 多标的请求按标的数乘以单标的行数估算；
- 日期范围按交易日保守估算，同时验证最早日期不超过套餐历史深度；
- 无行数概念的固定价接口只校验目录固定成本。

无法可靠解析请求规模的按量接口必须拒绝，不允许用不受控默认值绕过最大行数和预授权。

## 8. 计费与响应统计

固定价接口按 `base_cost` 预授权并结算。按量接口按请求允许的最大行数调用 `estimate()` 预授权，成功后从响应 JSON 中按该接口显式配置的 `result_path` 统计记录数，再调用 `calculate()` 结算。阶梯公式与已落地目录保持一致：首个 `unit_size` 包含在 `base_cost` 中，超出部分按 `ceil((actual_units - unit_size) / unit_size) * unit_cost` 累加并受 `max_cost` 限制。

每个按量接口必须在目录中配置确定的 `result_path`；不采用通用递归猜测。若响应契约与目录配置不匹配，视为服务端计费错误：释放全部冻结额、记录失败并返回 500。

- 2xx：按实际成本结算；
- 合法空结果：按目录公式结算；
- 4xx/5xx、异常、超时、响应统计失败：释放全部冻结额；
- 免费接口不创建零金额预约；
- `credential_id + request_id` 形成预授权幂等键；
- 客户端可传 `X-Request-ID`，仅接受 UUID；未提供则服务端生成。

响应头：

```text
X-Request-ID
X-DataHub-Endpoint
X-DataHub-Credits-Authorized
X-DataHub-Credits-Charged
X-DataHub-Credits-Remaining
X-DataHub-RateLimit-Limit
X-DataHub-RateLimit-Remaining
```

## 9. 调用统计

新增 `datahub_request_usage`，每次到达网关的请求写一行：请求 ID、用户、Credential、接口、状态码、请求量、实际量、授权积分、结算积分、耗时、错误代码和时间。不得保存 Key 明文、Authorization 头、完整查询数据或响应正文。

统计写入失败不得改变已完成的积分结算，但必须记录服务端日志；积分账本仍是余额权威来源。

## 10. HTTP API 与 Web 个人中心

新增登录态 API：

- `POST /api/datahub/credentials`
- `GET /api/datahub/credentials`
- `POST /api/datahub/credentials/{id}/rotate`
- `DELETE /api/datahub/credentials/{id}`
- `GET /api/datahub/usage`

创建与轮换响应返回一次性明文，列表只返回前缀、配置、最近使用时间和状态。

Web `/me` 增加“Data Hub”区域，包含：

1. Data Credit 余额、即将过期积分和本月消耗；
2. Credential 创建、轮换、吊销；
3. Scope、过期时间、IP 白名单配置；
4. 接口目录、权限状态和单次价格；
5. 按日期及接口汇总的请求量、成功率和积分消耗；
6. 一次性 Key 展示与复制警告。

## 11. 旧链路删除

同一个切换批次完成以下删除，不保留运行时兼容：

- `sigmx_routes.require_data_hub` 中的 `X-API-Key` 和 `api_key` 分支；
- `SubscriptionStore` 在 Data Hub 生产请求中的认证和配额用途；
- `datahub_auth.py` 的旧 `DataHubPrincipal` 和 `acquire_product_quota`；
- `/api/usage/me`；
- Data Hub 旧订阅管理路由和前端页面；
- 旧 `usage_daily` 请求次数写入；
- 声明 `sx_` Key 可用的测试、文档和注释。

旧数据库表可保留一个 schema 版本作为不可读取的孤立数据，以便回滚数据库文件；应用代码不得再查询。下一个 schema 清理版本再执行物理删除。

## 12. 错误码

网关返回稳定错误代码：

- `credential_required`：401
- `credential_invalid` / `credential_expired` / `credential_revoked`：401
- `ip_not_allowed`：403
- `dataset_not_entitled` / `scope_denied`：403
- `insufficient_data_credits`：402
- `request_rows_exceeded` / `history_depth_exceeded`：422
- `rate_limit_exceeded` / `concurrent_limit_exceeded`：429
- `endpoint_uncataloged` / `billing_contract_error`：500

错误响应同样包含 `X-Request-ID`，但不得暴露 Key 哈希、用户 ID、内部 SQL 或积分批次结构。

## 13. 测试与验收

必须证明：

1. 明文 Key 只出现一次，数据库和列表 API 不泄露；
2. 旧 `sx_`、`X-API-Key`、`api_key` 查询参数全部失效；
3. Key 吊销、过期、轮换和用户隔离正确；
4. Scope、IP、套餐数据组、行数和历史深度失败关闭；
5. 多 Key 共用用户级限流和并发限制；
6. 固定价、按量、空结果、异常释放和幂等重放正确；
7. 49 个接口全部经过网关且有唯一目录/响应统计配置；
8. 未登记接口无法启动或返回 500；
9. 激活与月度发放幂等；
10. Credential 和统计 API 只返回当前用户数据；
11. Web 控制台覆盖创建、一次性展示、轮换、吊销、余额和统计；
12. 日志、响应和审计不泄露秘密；
13. 产品域、Data Hub 路由和前端专项测试通过；
14. 生产构建通过。

## 14. 非目标

不实现企业组织、多租户、成员 RBAC、共享额度、合同权益、Credential 委派、OAuth Client Credentials、Redis 分布式限流、独立 API Gateway、数据积分购买支付或自动续费任务。上述能力不在当前个人产品架构内。
