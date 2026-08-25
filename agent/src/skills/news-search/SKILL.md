---
name: news-search
description: 财经领域为主的资讯搜索引擎，囊获了各类型媒体：官媒、主流财经媒体、垂直行业网站、知名上市公司/非上市公司官网等，可以帮助你了解最新财经事件、政策动态、行业革新、企业业务进展等等。
sigmx:
  schema_version: 1
  ownership: adapted
  execution: executable
  primary_source: public_source
  datahub_endpoints:
    []
  fallback_sources:
    - rsshub
  markets:
    - GLOBAL
  credentials:
    []
  capability_status: partial
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

当前能力由公共数据源（rsshub）提供；不得标记为 Data Hub 返回。 通过统一路由执行，并在结果中标明公共来源、时间和可用性限制。

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# 新闻搜索

## 定位

这是经过 SigmX 适配的数据研究 Skill。它保留原研究场景与稳定安装标识，但不再默认连接问财服务。

## 数据策略

主数据接口：

- 当前 Data Hub 尚无等价全文检索接口

候补数据源：rsshub。候补只在清单允许且能够保持指标口径时启用；结果必须展示实际来源、数据日期和降级原因。

## 执行

通过统一运行时请求数据：

```bash
python -m src.skill_runtime.cli capability_not_supported --params '{}'
```

执行前根据用户问题构造结构化参数，不得删除用户条件来制造结果。Data Hub 不支持所需能力且候补源也不能保持同一口径时，返回 `capability_not_supported`。

## 输出要求

- 展示实际数据源和数据日期；
- 解释筛选条件、指标单位与排序方法；
- 区分事实、计算结果和判断；
- 不把空数据解释为不存在候选；
- 结果不构成投资建议。
