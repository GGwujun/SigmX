---
name: sigmx-deploy
description: SigmX 本地/服务器部署自动化 skill
description_zh: SigmX 部署 skill（本地数据同步 + 服务器 Web 服务）
---

# SigmX 部署

根据用户需求选择部署模式：

## 本地部署（数据同步 + 离线分析）

**适用场景**：
- 开发者本地测试
- 离线环境分析
- 需要拉取最新行情数据并推送到服务器

**执行步骤**：

1. **检查环境**
   - 确认 Docker 和 Docker Compose 已安装
   - 确认 `agent/.env` 配置文件存在（不存在则从 `agent/.env.example` 复制）

2. **启动本地服务栈**
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.local.yml up -d
   ```

3. **验证部署**
   - 检查容器状态：`docker-compose ps`
   - 访问本地网站：`http://localhost:8900`
   - 查看数据推送日志：`docker logs sigmx-data-sync --tail 10`

4. **常用命令**
   - 停止服务：`docker-compose down`
   - 查看日志：`docker-compose logs -f [service]`
   - 重建容器：`docker-compose up -d --build`

## 服务器部署（生产环境）

**适用场景**：
- 公网 Web 服务
- 多用户访问
- 接收本地推送的数据

**执行步骤**：

1. **配置服务器**
   - 确认 `agent/.env` 配置（LLM API、管理员账号、JWT_SECRET）
   - 配置 `MARKET_SYNC_PUSH_TOKEN`（用于接收本地推送）

2. **启动服务**
   ```bash
   docker-compose up -d
   ```

3. **验证部署**
   - 访问公网地址：`https://sigmx.dsx-family.site`
   - 检查健康状态：`curl https://sigmx.dsx-family.site/api/v1/market/latest-trade-date`

4. **常用命令**
   - 更新镜像：`docker-compose pull && docker-compose up -d`
   - 查看日志：`docker-compose logs -f vibe-trading`
   - 重启服务：`docker-compose restart`

## 数据同步排查

**本地推送失败**：
```bash
# 检查推送日志
docker logs sigmx-data-sync --tail 50

# 常见错误：
# - 500 Internal Server Error：服务器 market.db 权限问题
# - Connection refused：服务器未启动或端口未开放
# - Token invalid：MARKET_SYNC_PUSH_TOKEN 不匹配
```

**服务器数据不更新**：
```bash
# 1. 检查本地是否拉取到新数据
sqlite3 data/market.db "SELECT MAX(trade_date) FROM bars_daily;"

# 2. 检查推送水位线
sqlite3 data/market.db "SELECT * FROM sync_meta WHERE key LIKE 'push:%';"

# 3. 手动重置水位线（强制重推）
sqlite3 data/market.db "UPDATE sync_meta SET value=NULL WHERE key LIKE 'push:%';"
docker-compose restart data-sync

# 4. 检查服务器 market.db 属主
ssh root@<server> "ls -lh /opt/sigmx/data/market.db"
# 应为 uid 1000 或 777 权限
```

## 端口说明

| 端口 | 服务 | 本地 | 服务器 |
|------|------|------|--------|
| 8900 | vibe-trading | ✅ | ✅ |
| 9000 | query-service | ❌（已合并到 8900）| ❌ |
| 11200 | rsshub | ✅（内部）| ✅（内部）|

## 查询 API

所有 `/api/v1/*` 接口**无需鉴权**，本地和服务器均可访问：

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

完整接口列表：[agent/src/api/sigmx_routes.py](agent/src/api/sigmx_routes.py)

## 架构说明

```
本地 Windows
├── market-sync（拉数据）→ 写 data/market.db
├── rsshub（RSS 源）
├── vibe-trading（本地网站，8900 端口）
└── data-sync（推送服务器，每 5 分钟）

服务器
├── vibe-trading（网站，8900 端口，含查询 API）
├── market-sync（可选，服务器也可拉数据）
└── rsshub
```

**数据流向**：外部数据源 → 本地 market-sync → data/market.db → data-sync → 服务器 market.db
