# calc 计算契约

所有数值计算走 `calculate` 工具（进程内确定性计算库），不心算。

## 工具入参

```json
{
  "function": "pct_change",
  "args": {"a": 444.64, "b": 453.90},
  "evidence_ids": ["ev-daily_basic_90d-3", "ev-daily_basic_90d-8"],
  "calculation_ids": [],
  "output_file": "01_yoy_change.json"
}
```

- `function`：函数名。想知道有哪些函数，调 `calculate` 传 `function: "list"`
  ——`list` 是元命令，只打印清单，不产生计算记录。
- `args`：该函数需要的实参（纯数据）。
- `evidence_ids`：这次计算直接用到的**证据行**编号，必须完整列出
  （少列 = 引用断裂，校验不过）。
- `calculation_ids`：这次计算用到的**上游计算**编号（同上，全列）。
- `output_file`：`NN_name.json` 形式（两位序号_小写下划线名），如
  `01_pe_percentile.json`。每个文件只能由创建它的阶段覆盖。

## 计算记录（信封）

每次调用落盘一条记录到 `calcs/NN_name.json`：

```json
{
  "calculation_id": "calc-1a2b3c4d5e6f7a8b",
  "fn": "pct_change",
  "args": {"a": 444.64, "b": 453.90},
  "status": "ok",
  "value": -2.044,
  "unit": "%",
  "reason": "",
  "calc_version": "1"
}
```

- `calculation_id` 由 `fn + 版本 + 规范化实参` 内容寻址生成：**同实参必同 id**。
  改写 value 骗不过校验（同实参会重算比对）。
- `status` 三档：
  - `ok`：有效计算，value 可引用；
  - `error`：入参错/未知函数等——错误记录也是审计痕迹，会落盘，但不算有效计算；
  - `not_meaningful`：算得出但无意义（NaN/Inf，如对负值开方），不算有效计算。
- error/not_meaningful 的记录**不要**引用进结论；修正 args 重算一条新的。

## 内置函数

| 函数 | 入参 | 说明 |
|---|---|---|
| `pct_change` | a, b | (a-b)/b 的百分比 |
| `ratio` | a, b | a/b |
| `diff` | a, b | a-b |
| `mean` | series | 均值 |
| `median` | series | 中位数 |
| `std` | series | 标准差（总体） |
| `zscore` | value, series | (value-mean)/std |
| `percentile_rank` | value, series | 历史分位百分比 |
| `max_drawdown` | series | 最大回撤百分比（绝对值） |
| `volatility` | series, periods_per_year=252 | 年化波动率% |
| `sum` | series | 合计 |
| `latest` | series | 末值 |

垂类插件可注册更多函数（以 `list` 输出为准）。

## 引用回填

阶段产物里引用计算结果时：

1. 把 `calculation_id` 填进产物顶层 `calculation_ids` 数组；
2. 正文里写数字时可以带 `[calc-xxx]` 编号；
3. 正文数字必须与记录的 `value` 一致（含单位换算：记录 0.498 写 49.8% 合法，
   写 49.83% 不合法——除非另有计算支撑）。

<!-- test-only -->
## 注册期自检（维护者看）

插件可声明 `self_test_calc` {fn, args, expect}：doctor 跑一次比对期望值，
防注册函数被误改。本段不注入提示词。
<!-- /test-only -->
