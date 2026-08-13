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

### 产品收口（套餐 / 积分 / 设备授权）

独立于旧兑换码体系，产品收口建立了可运营的套餐闭环（详见 `docs/superpowers/plans/2026-08-02-product-closure.md`）：

- **套餐目录**（服务端驱动，前端不硬编码价格）：免费版 / 进阶版 268 元/季 / 专业版 518 元/季 / 企业版。权益用稳定键（`datahub.daily_quota`、`desktop.device_limit` 等），不按中文名判断。
- **激活码开通**：运营在 `/admin/operations` 生成套餐激活码（SHA-256 哈希存储，明文仅显示一次）；用户在 `/account/subscription` 兑换，原子地创建零金额订单 + 发放权益 + 当月积分 + 审计。同一激活码全局单用，重复提交幂等不重复发放。
- **积分批次账本**（`product.db`）：月度套餐积分月底到期，购买/补偿积分永久；扣减顺序为过期优先；AlphaForge 失败自动退还且仅退一次。`/account/credits` 可看批次与流水。
- **设备授权**：桌面客户端通过 RFC-8628 风格 device-code flow 链接云账户，不复制密码。refresh token 经 Electron `safeStorage` 加密落盘，轮换 + 可撤销。`/account/devices/authorize` 浏览器侧批准。
- **Data Hub 双鉴权**：`/api/v1/*` 同时接受产品令牌（`aud=sigmx-product`）与旧 `sx_` API Key，按套餐 `datahub.daily_quota` 原子计量配额。旧 key 路径零感知。
- **欢迎积分**：新用户首次进入账户区自动获得 50 永久积分（懒发放，不改注册流程）。
- **迁移**：旧 `credits.db` 余额一次性迁移为永久批次（`legacy-credit-balance:<user_id>`），旧库保留可回滚。

后端领域层在 `agent/src/product/`（catalog / credits / commerce / devices / tokens / payment / datahub_auth），API 在 `agent/src/api/product_routes.py`，全部带 pytest 覆盖。

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

## 🗄️ 桌面客户端（本地优先架构）

SigmX 已迁移到**本地优先桌面客户端**架构。行情拉取、数据质量校验、Web UI 在同一个 Electron 进程里跑，无需远程服务器。数据存在 `~/.vibe-trading/market.db`（跨平台标准位置）。

### 架构

```
┌───────────────────────────────────────────────────────────────┐
│  SigmX.exe (Electron 桌面客户端)                                │
│                                                                 │
│  Electron 主进程 (Node)                                         │
│    ├─ spawn Python 后端 (单进程，含 serve + worker 线程)         │
│    │   ├─ FastAPI serve (UI + 查询 API /api/v1/*)              │
│    │   └─ market-sync worker (后台拉数据 + 质量门)              │
│    ├─ 打开原生 BrowserWindow → http://localhost:8899            │
│    └─ 退出时 taskkill 后端进程树                                 │
│                                                                 │
│  ~/.vibe-trading/                                               │
│    ├─ market.db                 ← 唯一数据源 (行情 + 指数 + 涨跌) │
│    ├─ users.db / sessions.db    ← 账户 / 会话                    │
│    └─ daily_recommendations.db  ← 推荐历史                       │
└───────────────────────────────────────────────────────────────┘
            ↑ 多源降级链
  tushare (1次/分钟) → tpdog (8万积分/天) → akshare → 腾讯 → 新浪
```

核心原则：
- **本地优先**：行情、UI、策略引擎都在本地。无远程依赖。
- **单进程**：serve 和 worker 在同一个 Python 进程，`VIBE_TRADING_START_MARKET_SYNC_WORKER=1` 开启。
- **数据自包含**：`market.db` 一个文件搞定，复制到哪都能用。
- **质量门 lenient 模式**：数据缺失（`received=0`）不阻断发布（区别于数据损坏 `valid=0`），避免源临时挂掉冻住整天数据。

### 启动

```bash
cd desktop
# 开发模式
$env:SIGMX_DEV='1'; $env:SIGMX_PYTHON='python'; node node_modules/electron/cli.js .

# 打包模式（PyInstaller bundle 就绪后）
npm start
```

登录后默认管理员 `admin@local / admin123`（首次启动自动注册）。

### 数据同步运维

```bash
# Electron 运行时 worker 自动拉数据。如需手动恢复某交易日：
cd agent
vibe-trading-sync once --date 2026-07-24

# 查看容器/进程日志
docker compose logs --tail 100  # 旧 docker 部署 (已淘汰)
```

`--no-shadow` 已移除。质量校验失败时，旧的 `market.db` 保持不变；通过 `GET /market-sync/status` 查看 `daily_readiness`、`run_id` 和阻断原因。

### 数据同步与 Data Hub（变现方向）

当前为纯本地模式。未来计划：
- **Data Hub**：服务器变成付费数据服务，运行完整降级链拉数据 + 对外只读 API
- **Connected 模式**：桌面客户端可选连接 Data Hub 拿更可靠的数据（订阅计费）
- 本地模式（Standalone）仍可用，免费分发，用户自带 tushare/tpdog token

### 停止客户端

关闭 Electron 窗口即停止所有服务（后端进程 + worker）。无后台残留。

### 端口与访问

| 端口 | 服务 | 说明 |
|------|------|------|
| 8899 | vibe-trading | Electron 内置 (含查询 API `/api/v1/*` + UI) |

桌面模式下 loopback 免 JWT 鉴权。远程访问需 Cloudflare Tunnel / Tailscale。

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
