# SigmX — AI 投研智能体平台

<p align="center">
  <b>面向 A 股投研场景的多智能体系统 · 个股深度报告 · 基金套利分析 · 量化因子</b>
</p>

---

## ✨ 项目简介

SigmX 是一套**面向 A 股为主的多智能体投研平台**，在 [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) 开源基础上扩展，内置完整的 Web 平台、用户体系与积分计费，开箱即用。

核心能力：
- **AlphaForge**：16-Agent 流水线，输入股票代码 → 自动产出多维度投研深度报告（技术面 / 基本面 / 新闻 / 情绪 / 政策 / 资金 / 解禁 + 多空辩论 + 交易决策 + 风控 + 最终裁决）
- **基金套利分析**：全市场 LOF/ETF 折溢价扫描 + 单基金 6-Agent 深度套利报告
- **量化因子工厂**：452 个预构建 Alpha 因子（alpha101 / gtja191 / qlib158 / academic）
- **多智能体协作**：基于 DAG 的 swarm 编排，支持并行 / 辩论 / 裁决
- **用户体系**：注册登录 + 免责声明 + 积分计费 + 兑换码 + 管理员权限
- **消息推送**：飞书 / 钉钉 / 企业微信群机器人通知

---

## 🧩 功能模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 今日总览 | `/` | 机会 / 报告 / 回测汇总，缓存秒开 |
| 智能体 | `/agent` | 自然语言对话式投研，可读数据 / 网页 / 文件 |
| AlphaForge | `/alpha-forge` | 16-Agent 个股深度投研报告（消耗积分）|
| 套利机会 | `/fund-opportunity` | 全市场 LOF/ETF 折溢价扫描排行 |
| 套利分析 | `/fund-arbitrage` | 6-Agent 单基金深度套利报告（消耗积分）|
| 因子工厂 | `/alpha-zoo` | 452 个 Alpha 因子浏览 / 回测（**仅管理员**）|
| 跟踪看板 | `/tracking-dashboard` | 趋势 / 资金 / 事件 / 风险多维度仓位审视 |
| 机会清单 | `/opportunity` | 系统扫描的候选标的 |
| 逻辑链 | `/logic-chain` | 宏观到交易的分层推理 |
| 新闻 / 事件 | `/news` `/events` | 市场情报 |
| 个人中心 | `/account` | 账户 / 积分 / 兑换码 / 流水 / 改密 |
| 设置 | `/settings` | 模型与数据源（**仅管理员**）+ 通知配置 |

---

## 🚀 快速开始

### 方式 A：Docker 部署（推荐生产环境）

```bash
git clone https://github.com/GGwujun/SigmX.git
cd SigmX

# 配置环境变量
cp agent/.env.example agent/.env
# 编辑 agent/.env，至少配置 LLM、管理员账号、JWT_SECRET

# 构建并启动
docker compose up -d --build
```

访问 `http://服务器IP:8899`，默认管理员账号 `admin@sigmx.local / admin123`（**生产环境务必在 .env 改密码**）。

### 方式 B：本地开发

```bash
# 后端
pip install -r agent/requirements.txt
pip install -e .
vibe-trading serve          # 启动 API + 前端 dist（默认 8000 端口）

# 前端热更新（可选）
cd frontend
npm install
npm run dev                 # 5899 端口
```

---

## 🔐 用户与权限

- **注册登录**：邮箱 + 密码，本地访问也需登录，JWT 24h
- **免责声明**：注册勾选 + 登录后弹窗确认，全页水印「仅供学习研究，不构成投资建议」
- **积分体系**：AlphaForge 报告 50 积分，基金套利 20 积分；余额不足拒绝；分析失败自动退还
- **兑换码**：管理员用脚本批量生成，用户兑换获得积分
- **管理员**：默认账号 `admin@sigmx.local`，可查看因子工厂与系统配置

### 生成兑换码

```bash
python agent/scripts/gen_codes.py --credits 100 --count 50 --days 90
# → 写入 credits.db + 导出 ~/credits_codes_<时间戳>.csv
```

---

## 🔔 消息推送

设置页 → 通知配置，支持三平台群机器人：
- **飞书**：自定义机器人 + 签名校验
- **钉钉**：自定义机器人 + 加签
- **企业微信**：群机器人（key 鉴权）

配置后点「测试发送」会推送实时行情摘要到群。

---

## ⚙️ 环境变量

关键配置（`agent/.env`）：

| 变量 | 说明 | 必填 |
|------|------|------|
| `LANGCHAIN_PROVIDER` / `LANGCHAIN_MODEL_NAME` | LLM 供应商与模型 | ✅ |
| `ZHIPU_API_KEY` / `OPENAI_API_KEY` 等 | 对应供应商的 key | ✅ |
| `TUSHARE_TOKEN` | A 股数据（tushare）| 分析 A 股需要 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | 管理员账号 | 建议 |
| `JWT_SECRET` | JWT 签名密钥（固定值，否则重启 token 失效）| 建议 |
| `API_AUTH_KEY` | 远程访问备用 key | 公网部署建议 |

---

## 🏗️ 技术栈

- **后端**：Python 3.11+ / FastAPI / SQLite（users.db / credits.db / sessions.db）
- **前端**：React + TypeScript + Vite + Tailwind
- **多智能体**：自研 swarm DAG 编排框架（YAML 预设）
- **数据源**：Tushare（规范日线）/ TPDog（补缺与交叉校验）/ mootdx / akshare
- **LLM**：OpenAI 兼容接口（智谱 GLM / DeepSeek / OpenAI / Moonshot 等）

---

## 🗄️ 本地数据同步

行情拉取与业务查询严格分进程运行。`market-sync` 是唯一允许访问外部行情源并写入规范市场库的服务；`vibe-trading` 只读取已经发布的数据。

### 架构

```
外部数据源
└── market-sync（唯一写入者）
    ├── 写 shadow DB
    ├── 校验交易日、覆盖率、OHLC、停牌、来源与跨源样本
    └── 仅 verified 后发布到 market.db

market.db（规范库）
└── vibe-trading（只读查询与推荐）
```

严格模式遵循以下规则：

- 缺数据优于错数据；实时快照永远不能转换成规范日线。
- 每次同步都有 `run_id`、来源、质量状态和阻断原因。
- `partial`、`failed`、`quarantined` 不发布，也不写每日成功标记，Worker 会继续重试。
- 每日推荐只接受目标交易日状态为 `verified` 或 `published` 的数据。
- `/market-sync/daily`、`/market-sync/code`、`/market-sync/backfill`、`/market-sync/push` 均为只读服务禁用接口，返回 `SYNC_WORKER_REQUIRED`。

### 启动本地环境

```bash
# 配置环境变量（首次部署）
cp agent/.env.example agent/.env
# 编辑 agent/.env，配置 LLM、管理员账号、JWT_SECRET 等

# 启动本地服务栈
docker-compose -f docker-compose.yml -f docker-compose.local.yml up -d

# 查看状态
docker-compose ps
```

### 端口与访问

| 端口 | 服务 | 说明 |
|------|------|------|
| 8900 | vibe-trading | 本地网站（含查询 API `/api/v1/*`）|
| 11200 | rsshub | RSS 数据源（内部使用）|

访问 `http://localhost:8900`，默认管理员 `admin@sigmx.local / admin123`。

### 查询 API（无鉴权）

本地和服务器都提供 `/api/v1/*` 查询接口（公开访问，无需 token）：

```bash
# 最新交易日
curl http://localhost:8900/api/v1/market/latest-trade-date

# 指数行情
curl http://localhost:8900/api/v1/indices/daily

# 盘前三图
curl http://localhost:8900/api/v1/content/morning-briefing-triptych

# Swagger 文档
open http://localhost:8900/docs
```

完整接口列表见 [agent/src/api/sigmx_routes.py](agent/src/api/sigmx_routes.py)。

### 同步运维

生产环境只运行独立 Worker：

```bash
# 持续同步
vibe-trading-sync worker --interval 60

# 手工恢复指定交易日（强制 shadow 校验与发布）
vibe-trading-sync once --date 2026-07-14

# 查看容器日志
docker compose logs market-sync --tail 100
```

`--no-shadow` 已移除。质量校验失败时，旧的 `market.db` 保持不变；通过 `GET /market-sync/status` 查看 `daily_readiness`、`run_id` 和阻断原因。

### 数据同步与线上查询的部署边界

推荐部署为两个主机角色：

- 同步主机运行 `market-sync` 和 `data-sync`，二者挂载同一个 `market.db`。前者只负责拉取、影子库校验和发布，后者只发送已发布快照。
- 线上查询主机运行 `vibe-trading` 和 `data-ingest`。查询 API 不访问外部行情源；`data-ingest` 是独立控制面，只接收并校验快照，再导入共享数据库卷。

生产查询主机默认不会启动 `market-sync`。只有同步主机才显式启用：

```bash
docker compose --profile sync up -d market-sync
```

在两端设置相同的高强度 `MARKET_INGEST_TOKEN`。发送端的 `MARKET_INGEST_URL` 指向接收 sidecar；如果通过 Nginx 暴露 `/market-ingest/`，需将此前缀剥离后代理到 `127.0.0.1:8898`。也可以通过受限专网直接连接 8898。不要把该端口公开到互联网明文访问。

默认快照发送时点是 `09:26`、`14:29`、`15:20`，分别服务于 `09:27`、`14:30` 今日推荐和收盘后正式数据。可通过 `SNAPSHOT_PUSH_SLOTS` 调整。传输支持断点续传和幂等重试；接收端只有在 SHA-256、SQLite 完整性及对应 `sync_runs.status=published` 全部通过后才提交。

```bash
# 查询主机（业务查询 + 接收控制面，不拉行情）
docker compose up -d vibe-trading data-ingest

# 查看交付状态
docker compose logs data-ingest --tail 100
```

### 停止本地服务

```bash
docker-compose -f docker-compose.yml -f docker-compose.local.yml down
```

---

## 📂 项目结构


```
├── agent/                  后端
│   ├── src/
│   │   ├── api/            HTTP 路由（auth/credits/fund/notify/alpha_forge/sigmx...）
│   │   ├── auth/           用户认证（JWT + bcrypt + users.db）
│   │   ├── credits/        积分体系（balance/transactions/redeem）
│   │   ├── notify/         消息推送（飞书/钉钉/企业微信）
│   │   ├── data/           数据层（fund_premium 折溢价等）
│   │   ├── swarm/          多智能体 DAG 编排 + presets/
│   │   └── factors/zoo/    452 个 Alpha 因子
│   ├── api_server.py       FastAPI 入口
│   └── scripts/            兑换码生成等工具
├── frontend/               前端（React + TS）
│   └── src/pages/          页面（AlphaForge/FundArbitrage/Account...）
├── Dockerfile
├── docker-compose.yml      服务器默认配置
├── docker-compose.local.yml 本地部署覆盖配置
└── pyproject.toml
```

**数据目录**（与代码分离）：
- `E:\gwj\sigmx-local\data\` — 本地数据库文件（market.db、sessions.db 等）
- 通过 `docker-compose.local.yml` 挂载到容器内 `/data`

---

## ⚠️ 免责声明

本系统生成的市场分析、交易观点、回测结果和对话内容**仅供学习研究与信息参考**，不构成任何投资建议、收益承诺或交易指令。金融市场存在风险，历史表现不代表未来结果，请结合自身风险承受能力独立判断。

---

## 📜 致谢

本项目基于 [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) 二次开发，感谢原作者的开源贡献。

## License

MIT
