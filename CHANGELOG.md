# 更新日志

本项目基于 [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) 二次开发。

## 2026-06-14 — SigmX 投研平台

### 新增
- **AlphaForge 个股投研**：16-Agent 流水线（数据采集 → 7 维研究 → 质量门控 → 多空辩论 → 交易决策 → 风控 → PM 裁决 → 报告总撰），集成 452 个 Alpha 因子交叉验证，共享事实表消除数据冲突，输出连贯综合研报
- **基金套利分析**：全市场 LOF/ETF 折溢价扫描（ths 净值 + mootdx 场内价）+ 6-Agent 单基金深度套利报告
- **用户体系**：邮箱注册登录（JWT），本地也要登录，免责声明（注册勾选 + 登录弹窗 + 全页水印）
- **积分计费**：credits.db 三表，并发安全扣费，分析失败自动退还，兑换码批量生成
- **个人中心**：账户信息 / 积分余额 / 兑换码 / 流水 / 改密 / 退出登录
- **消息推送**：飞书 / 钉钉 / 企业微信群机器人配置 + 测试发送（实时行情摘要）
- **管理员权限**：默认管理员账号，因子工厂 + 系统配置仅管理员可见，前后端双重保护

### 优化
- 今日总览 stale-while-revalidate 缓存（秒开 + 后台刷新）
- `read_url` 国内直连回退（避开境外 Jina）
- `web_search` Bing + 东方财富多源回退（解决 DDG 中文无结果）
- 设置页加通知配置 Tab，平台子 Tab 切换
- 401 自动跳登录页

### 部署
- Dockerfile 多阶段构建，非 root 运行，持久化数据目录
- docker-compose 持久卷（runs / sessions / data）
- 补齐 pyjwt / bcrypt / markdown 等依赖

---

## 基础能力（继承自 Vibe-Trading）

- 自然语言投研智能体（FastAPI + ReAct）
- 7 引擎回测（ChinaA / GlobalEquity / Crypto / Futures / Forex + Options）
- 多数据源（tushare / yfinance / okx / akshare / mootdx / ccxt / futu）
- Alpha Zoo 452 个因子（alpha101 / gtja191 / qlib158 / academic）
- 多智能体 swarm 编排（29 个预置团队）
- Shadow Account 交易日记分析
