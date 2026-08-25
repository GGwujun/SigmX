---
name: hithink-basicinfo-query
description: 查询全品类标的（股票、指数、基金、期货、期权、转债、债券、理财、保险等）的基础信息、发行主体、机构资料、费率、上市地点、上市日期等静态信息，支持自然语言问句输入，返回相关基本资料数据结果。当用户询问股票基本信息、基金资料、期货合约信息、债券资料、费率信息、上市日期等基本资料查询问题时，必须使用此技能。
sigmx:
  schema_version: 1
  ownership: adapted
  execution: executable
  primary_source: data_hub
  datahub_endpoints:
    - stocks.metadata
  fallback_sources:
    - akshare
  markets:
    - CN_A
  credentials:
    - SIGMX_DATA_HUB_BASE_URL
    - SIGMX_DATA_HUB_KEY
  capability_status: partial
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

默认且优先使用 SigmX Data Hub；只在清单声明允许且指标口径一致时使用候补源。 `python -m src.skill_runtime.cli stocks.metadata --params '<JSON>'`

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# 公司基本资料查询

## 定位

这是经过 SigmX 适配的数据研究 Skill。它保留原研究场景与稳定安装标识，但不再默认连接问财服务。

## 数据策略

主数据接口：

- `stocks.metadata`

候补数据源：akshare。候补只在清单允许且能够保持指标口径时启用；结果必须展示实际来源、数据日期和降级原因。

## 执行

通过统一运行时请求数据：

```bash
python -m src.skill_runtime.cli stocks.metadata --params '{}'
```

执行前根据用户问题构造结构化参数，不得删除用户条件来制造结果。Data Hub 不支持所需能力且候补源也不能保持同一口径时，返回 `capability_not_supported`。

## 输出要求

- 展示实际数据源和数据日期；
- 解释筛选条件、指标单位与排序方法；
- 区分事实、计算结果和判断；
- 不把空数据解释为不存在候选；
- 结果不构成投资建议。
