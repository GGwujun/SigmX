/**
 * 交易工作台入口开关。
 *
 * 2026-10-23 产品决策（双端 agent 分工）：web = 在线研究问答，desktop = 专业
 * 本地分析工作台，**交易两边都不做**——A 股没有面向个人的程序化下单 API，
 * 已接的连接器（Robinhood/IBKR/Futu/Alpaca/Binance/Dhan）全是境外券商，
 * 对目标用户是不可用功能。桌面端隐藏交易入口；`agent/src/live/` 后端与
 * mandate/halt 安全机制代码全部保留，翻回 true 即可恢复。
 */
export const TRADING_UI_ENABLED = false;
