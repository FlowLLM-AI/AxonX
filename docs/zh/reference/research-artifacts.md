---
title: 研究产物与 Studio 展示协议
description: 标准研究输出、文件摘要、训练曲线及回测表的生产和读取契约。
---

# 研究产物与 Studio 展示协议

研究 Task 使用类型化 `output_params` 发布结果，Studio 从成功任务的 `metadata.json` 提取展示字段，再通过文件预览读取产物。本页区分三层要求：Python 基类必填字段、Studio 实际读取字段、具体插件的扩展协议。

![产物阅读链](../../figures/research/results-reading.svg)

## metadata 与产物映射

标准 Task 记录在 metadata 顶层保存身份、输入参数、输出参数等信息；研究字段位于 `output_params`，不要把它们写到顶层期待 Studio 自动识别。

以下是结构片段，不是完整 TaskMetadata：

```json
{
  "output_params": {
    "artifacts": {
      "dataset": {
        "path": "alpha158.parquet",
        "size": 1024,
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
      }
    }
  }
}
```

示例 size 和摘要只是说明字段；实际必须从生成文件计算。`artifact_record(path, task_dir)` 会生成相对路径、字节大小与 SHA-256。`artifact_path(task_dir, metadata, name)` 解析记录并拒绝绝对路径或越出任务目录的路径。

`BaseOutputParams.artifacts` 默认空字典，类型是 `dict[str, dict[str, Any]]`。因此 Python 基类没有完整校验每条 artifact 的三字段；生产者应主动调用 helper，确保页面和下游能读取。

下游 helper 解析路径本身并不自动核验所有摘要。qlib_a158 预测另行校验模型摘要，不能据此宣称所有上游数据均经过完整校验。

## 五类基础输出

下表的必填指模型没有默认值；不是所有字段都在 Studio 单独展示。

| 类型     | 基类必填                                       | 基类可选或默认字段                                             |
| -------- | ---------------------------------------------- | -------------------------------------------------------------- |
| ETL      | `output_file`、`rows`、`date_range`            | `feature_columns=[]`、`label_columns=[]`                       |
| Analysis | `result_file`、`rows`                          | `scores={}`                                                    |
| Train    | `model_file`、`train_rows`                     | `model_name`、特征/目标列、metrics、parameters、training_curve |
| Predict  | `predictions_file`、`rows`、`date_range`       | `output_columns=[]`、`protocol={}`、`statistics={}`            |
| Backtest | `dimensions`、`protocol`、`date_range`、`days` | 共享的 `artifacts={}`                                          |

所有类型继承 `BaseOutputParams`；额外字段需通过输出子类声明，否则 `extra=forbid` 校验失败。`date_range` 是字符串映射，页面按 `start` 与 `end` 取值，生产者应采用这些 key。

## ETL 产物

基类保存输出文件描述和列名。qlib_a158 扩展 feature_count、symbols、schema、protocol、market_state 等信息，生成：

| artifact 名  | 文件               | 用途                               |
| ------------ | ------------------ | ---------------------------------- |
| `dataset`    | `alpha158.parquet` | 训练、因子分析和预测的源数据       |
| `statistics` | `alpha158.csv`     | 各列质量统计                       |
| `labels`     | `labels.parquet`   | 固定次一市场日原始收益及可用状态   |
| `market`     | `market.parquet`   | 报价、复权因子、成交资格及行情状态 |
| `calendar`   | `calendar.parquet` | 独立于预测资格的市场日期           |

qlib_a158 下游通过 `artifacts.dataset.path` 解析数据，不能仅填写 `output_file` 而省略映射。输出文件字段保存完整字符串路径，而标准 artifact 应是 Task 目录内相对路径。

## 因子分析 scores

`scores` 的形状为“分组名 → 指标名 → 数值”：

```json
{
  "scores": {
    "quality": { "mean_abs_ic": 0.03, "positive_ratio": 0.6 },
    "coverage": { "valid_days": 120.0 }
  }
}
```

这只是合法形状示例，不是 qlib_a158 的固定指标集合。Studio 动态遍历分组及指标，插件应保证指标名与定义可理解，并在详细文件或扩展定义字段交代样本、单位和计算范围。

qlib_a158 实际生成 `factor_analysis.csv`、`factor_quantiles.csv`，映射名分别为 `result`、`quantiles`，并保存 definitions、labels 等扩展字段。

## 训练曲线模型

`TrainingCurve` 是明确验证的模型：

```json
{
  "x": ["1", "2", "3"],
  "y_left": {
    "train_l2": [0.09, 0.07, 0.06],
    "validation_l2": [0.1, 0.08, 0.085]
  },
  "y_right": {
    "validation_l1": [0.22, 0.2, 0.205]
  }
}
```

必须满足：

- x 是有序字符串标签，各序列按相同位置对齐。
- 每条序列长度严格等于 x 长度，数值均为有限值。
- 有 x 时至少存在一条左轴序列；右轴不能单独存在。
- 左右轴序列名称不能重复。
- 空 x 且左右组都为空表示没有曲线数据。

左轴同组应采用相近量纲和数值范围，右轴仅用于第二组尺度。协议不支持第三个数值轴。Studio 读取端只做轻量规范化；图表过滤长度不匹配的序列，计算轴范围时忽略非有限值，不会完整复验 Python 模型规则，也不会修复训练历史。生产者必须在发布前用模型验证。

qlib_a158 把 L2 放左轴、L1 放右轴；曲线是调参模型的训练/验证历史。`model`、`feature_importance`、`evaluation_history` 分别引用最终模型、重要性和历史 CSV。

## 预测统计

基类 `statistics` 是自由扩展映射。Studio 当前读取：

```text
statistics.days / symbols
statistics.pred.mean / min / median / max
statistics.buyable_rows / candidate_rows
statistics.indices.<column>.constituents / days_with_weights / null_rows
```

缺少这些字段时页面显示空值，不意味着所有预测插件都必须提供 qlib_a158 股票统计。qlib_a158 artifact 名为 `predictions`，文件为 `predictions.parquet`。

股票回测使用 `axonx.task.builtins.stock` 的统一契约。预测行包含 `trade_date`、`trade_time`、`ts_code`、`pred`、`is_model_candidate`、`is_buyable_at_signal`、`signal_price` 和 `signal_adjustment_factor`；资格标志是非空 Boolean。qlib_a158 另外输出 `name`、`rank`、`buyable_rank` 和指数权重。预测不包含未来标签。ETL 独立发布 `dataset`、`labels`、`market`、`calendar`；`labels` 按信号主键存储 `label_target_date`、`label_return`、`label_valid`、`label_status`。Rank/CSZ 目标仅在训练完成截止时间及样本筛选后计算。

## 预测到股票回测的输入契约

`BaseStockBacktestTask` 从预测 Parquet 读取以下 8 个必需列；两个 Alpha158 插件的 `predictions.parquet` 都满足该契约。

| 必需列                     | 类型与约束                                      | 含义                                       |
| -------------------------- | ----------------------------------------------- | ------------------------------------------ |
| `trade_date`               | 非空字符串，有效 YYYYMMDD，且属于市场日历       | 信号日期                                   |
| `trade_time`               | 非空字符串，有效 HHMM；一次回测只能包含一个时点 | 信号时点，例如 `1500`                      |
| `ts_code`                  | 非空字符串                                      | 股票标识                                   |
| `pred`                     | 非空、有限数值                                  | 排序分数，越大排名越靠前；不是收益率或概率 |
| `is_model_candidate`       | 非空 Boolean                                    | 是否具有模型候选资格                       |
| `is_buyable_at_signal`     | 非空 Boolean                                    | 信号时是否满足可买筛选条件                 |
| `signal_price`             | 非空、有限数值                                  | 信号时参考报价，与复权因子分开存储         |
| `signal_adjustment_factor` | 非空、有限数值                                  | 信号时参考报价的复权因子                   |

预测表不能为空，组合主键 `(trade_date, trade_time, ts_code)` 必须唯一且无空值。股票标识和时点需与行情表使用相同口径。参考报价和复权因子按其价格含义应为正值。两个资格标志都为 `true` 的行才进入选股候选池，再按 `index_codes` 筛选。

以下列不是基础回测的必需列：

| 可选列                 | 用途                                                                                                                                   |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                 | 明细显示名称；省略时使用 `ts_code`                                                                                                     |
| `rank`、`buyable_rank` | 预测侧辅助排名；回测自行按 `pred` 降序、`ts_code` 升序计算目标排名                                                                     |
| `index_weight_<code>`  | 小数单位指数权重；配置 `index_codes=["hs300"]` 时必须提供 `index_weight_hs300`，权重大于零表示属于该候选指数；权重列也用于基准收益代理 |

预测无需提供特征列、`actual_return`、未来标签或未来买卖日期。`signal_price` 和 `signal_adjustment_factor` 是信号参考信息；实际成交与逐日估值使用独立 `market` 表中的 `price`、`adjustment_factor` 和交易状态。

回测输入还需独立的 `market` 和 `calendar` 产物；可选 `labels` 用于 IC、RankIC、NDCG、目标标签收益和基准收益，无标签时仍可运行组合账本。指定文件时分别传 `input_file`、`market_file`、`calendar_file` 和可选 `labels_file`，上述 `input_file` 为预测 Parquet。

通过 Predict Task ID 解析时，预测 metadata 的 `output_params.artifacts.predictions` 必须提供产物记录（相对 `path`、`size`、`sha256`），并声明 `output_params.protocol.version=2`。`protocol.market_source_task` 指向提供行情、日历和标签的 ETL Task；也可在 `source_tasks` 显式指定 ETL 来源或传入对应文件路径。任务解析会校验来源产物摘要。`statistics` 是展示信息，不是回测选股输入。

## 回测 dimensions 与 protocol

```json
{
  "dimensions": {
    "top_ns": [1, 5, 10, 30],
    "holding_detail_top_n": 30,
    "benchmarks": [{ "key": "universe", "label": "Universe" }]
  },
  "protocol": { "version": 2, "return_unit": "decimal" },
  "date_range": { "start": "20230103", "end": "20231229" },
  "days": 250
}
```

这是基类合法结构示例。统一股票 Task 在 `protocol` 中发布执行、估值、配置、费用、截止时间和输入摘要的定义，`evaluation_status` 标识行情不完整的结果。页面不是自动验证协议文字的回测引擎；插件作者需明确真实执行与单位。

Studio 从 `artifacts.daily.path` 和 `artifacts.summary.path` 加载两个表，加载时每页请求 5000 行，根据 `has_more` 继续，直到读取完整表。仅满足 Backtest 输出模型不足以保证图表可用。

## 日频表的展示字段

| 字段                                     | 当前 Studio 用途                                 |
| ---------------------------------------- | ------------------------------------------------ |
| `trade_date`                             | 日期轴与两个策略的日期配对，采用 YYYYMMDD 字符串 |
| `candidate_count`                        | 候选数量                                         |
| `ic`、`rank_ic`                          | 信号曲线及移动均值                               |
| `topN_net_return`、`topN_gross_return`   | 净复利、毛累加曲线                               |
| `topN_turnover`、`topN_transaction_cost` | 换手和成本观察                                   |
| `topN_ndcg`                              | 各配置 Top N 规模的排名诊断                      |
| `benchmark_<key>_return`                 | dimensions 声明的基准收益曲线                    |
| `top30_holdings`                         | 当前固定 Top 30 明细                             |

明细是结构数组，前端读取 `rank`、`ts_code`、`name`、`prediction`、`daily_return`、`weight`。`daily_return` 是固定次一市场日标签，在截止时间不可用时为空。真实买卖日期和延期退出保存在 `positions`、`trades`；成交与未成交原因保存在 `orders`。

当前页面硬编码 `top30_holdings`，不会因 holding_detail_top_n 的值改变而自动寻找新列。qlib_a158 这个字段是信号目标、包含未成交候选；不能描述为实际持仓账本。

## 汇总表的展示字段

每行用 `period_type` 标明 `overall`、`year`、`quarter` 或 `month`，并提供 `period`、`period_start`、`period_end`、`trading_days`。

信号字段包括 `ic_mean`、`icir` 和 `rank_ic_mean`。每个 Top N 对应：

```text
topN_net_cumulative_return
topN_net_annualized_return
topN_net_annualized_volatility
topN_net_max_drawdown
topN_net_win_rate
topN_average_turnover
topN_gross_cumulative_return
topN_gross_sharpe
topN_information_ratio_<benchmark key>
```

N 替换为 dimensions 中的实际数字。汇总表是插件输出；收益图和策略比较是浏览器计算。qlib_a158 毛累计汇总用复利，毛收益图用累加，口径说明见[回测解读](../research/backtest.md)。

## 生产者验收

1. 用实际输出子类验证 output_params。
2. 先写文件，再调用 artifact_record 并发布 metadata。
3. 从 Task 目录用 artifact_path 解析每个标准 artifact。
4. 对照当前 Studio 字段检查日期、数值单位、布尔列和结构数组。
5. 验证曲线与下游契约，保留 protocol 的明确执行说明。

不要手工用占位摘要冒充真实文件；也不要修改 metadata 来掩盖失败执行。所有图表依赖相应生产者和读取端的共同契约。

## 实现依据

- [`基础研究模型`](../../../axonx/task/contracts/)
- [`产物 helper`](../../../axonx/task/storage/artifacts.py)
- [`Studio 读取映射`](../../../axonx_studio/src/features/research/ResearchPage.tsx)
- [`回测展示类型`](../../../axonx_studio/src/features/research/backtest/types.ts)
- [`qlib_a158 输出实现`](../../../plugins/qlib_a158/axonx_qlib_a158/)
