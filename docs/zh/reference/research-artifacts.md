---
title: 研究产物与 Studio 展示协议
description: 标准研究输出、文件版本、训练曲线及回测表的生产和读取契约。
---

# 研究产物与 Studio 展示协议

研究文件记录统一使用 `revision="<size>:<mtime_ns>"`，不计算文件内容摘要。产物发布、上游输入读取、在线历史仅检查文件属性，复制时保留纳秒修改时间；已发布文件必须保持不可变，通过原子替换更新。大小与修改时间都未变化的内容修改无法被检测。模型身份对成员版本计算指纹，配置和源码仍保留 SHA-256。

研究 Task 使用类型化 `output_params` 发布结果，Studio 从成功任务的 `metadata.json` 提取展示字段，再通过文件预览读取产物。本页区分三层要求：Python 基类必填字段、Studio 实际读取字段、具体插件的扩展协议。

数据表使用 `<名称>.parquet`；CSV 仅用于统计报表，所有 CSV 文件名都以 `_stats.csv` 结尾。例如 `features.parquet` 对应 `features_stats.csv`，`alpha158.parquet` 对应 `alpha158_stats.csv`。实时窗口和逐股票预测差异保留 Parquet。执行记录、模型原生文件、Markdown 报告及分层 JSON 报告使用各自格式。

## 统一协议 v1

AxonX 在 `axonx.task.models.artifacts` 中统一定义研究协议。研究协议头必须包含 `version=1`，在 `task_type` 中使用 `TaskType` 的值。读取时拒绝缺少协议头和其他版本的数据。

一次训练计划只有一个 Task ID，所有 seed 与 rolling 窗口共用 `metadata.json.output_params` 中的 `BaseTrainOutputParams`。`feature_protocol` 与 `training_target` 保存共享契约；`model_groups` 按时间保存共享训练和使用区间的模型组，组内 `models` 按名称保存各成员有效配置、状态、样本数、参数、指标、曲线与耗时。成员通过 `model_artifact` 引用 `artifacts`，最终模型打平放在 `models/`。预测按 `[use_from,use_to)` 选组；末组 `use_to=null`，持续服务后续日期。

每个离线预测 Task 只发布一个 `predictions.parquet`，包含全部日期、seed 和分数列。股票行以 `(trade_date, trade_time, ts_code)` 唯一标识。`metadata.json.output_params.protocol` 保存 `score_columns` 和按时间有序、不重叠的 `windows`；每个窗口记录 `[prediction_start,prediction_end_exclusive)`、分数成员到训练模型名称的 `models` 映射，以及该组 `model_identity`。消费者按预测日期选择窗口。完整模型配置保留在训练 metadata，生产执行及消费的文件修订保留在 `input_sources`。预测文件路径、大小和修订只放在 `output_params.artifacts.predictions`；实际日期保存在 parquet，输出 metadata 仅保留 `rows`、`date_range`、`output_columns` 和可选 `statistics` 等轻量摘要。预测始终写入 Task 自有目录。rolling 父任务保存自己的 `predictions.parquet` 快照，避免可复用子任务覆盖父任务已发布的结果。

在线预测使用同一个 `PredictionProtocol` 分数映射，类型为 `inference`，保存在 Task metadata 的已发布 commit 中；模型身份、日期、时刻和产物记录由 commit 持有，不再增加模型窗口或协议文件。Qlib 插件使用 `models_sha256` 和 `features_sha256` 身份项；共享窗口类型允许插件定义字符串键和值。Qlib 特征契约与指纹由 `axonx_qlib_a158.internal.modeling` 提供；语义指纹覆盖计算规则与有序特征，排除位置、日期覆盖和质量计数。软件包发布版本独立管理。

Qlib 特征契约使用一份有序的 `feature_columns` 列表，模型记录实际选择的子集及顺序。信号资格统一为 `is_buyable_at_signal`，市场执行条件保留 `can_buy` 和 `can_sell`。训练报告通过 `metrics` 发布验证指标，并分别记录裁剪前后及调参/验证样本数。

## metadata 与产物映射

标准 Task 记录在 metadata 顶层保存身份、输入参数、输出参数等信息；研究字段位于 `output_params`，不要把它们写到顶层期待 Studio 自动识别。

Task 输入通过 `input_sources` 保存生产执行与产物修订。显式外部预测文件没有生产 Task 引用，Portfolio 只在 `protocol.input_revisions` 中保存一次其修订。

以下是结构片段，不是完整 TaskMetadata：

```json
{
  "output_params": {
    "artifacts": {
      "dataset": {
        "path": "alpha158.parquet",
        "size": 1024,
        "revision": "1024:1700000000000000000"
      }
    }
  }
}
```

示例 size 和版本只是说明字段；实际必须从生成文件计算。`artifact_record(path, task_dir)` 会生成相对路径、字节大小与文件版本。`verify_artifact(task_dir, ArtifactRecord.model_validate(record))` 解析记录，核验普通文件的大小和版本；拒绝越出 Task 目录或经过符号链接的路径。

`BaseOutputParams.artifacts` 使用 `dict[str, ArtifactRecord]`，统一校验任务内相对路径、非负文件大小和文件版本。通过 `task.artifact_path(name)` 解析产物，无需额外绝对路径字段。

`task.artifact_path(name)` 解析输出路径。`upstream_artifact()` 和 `upstream_artifacts()` 校验成功、非展示副本的上游，并直接读取其发布文件。Task metadata 通过 `input_sources` 记录来源执行与文件修订；执行结束前再次核验，来源被替换或文件变化则失败。revision 使用大小与纳秒修改时间，并非内容哈希；业务兼容性仍由插件检查。

## 研究阶段输出

下表的必填指模型没有默认值；不是所有字段都在 Studio 单独展示。

| 类型      | 基类必填                           | 基类可选或默认字段                       |
| --------- | ---------------------------------- | ---------------------------------------- |
| ETL       | `rows`、`date_range`               | `feature_columns=[]`、`label_columns=[]` |
| Analysis  | `rows`                             | `scores={}`                              |
| Train     | `feature_protocol`, `model_groups` | `training_target={}`, `artifacts={}`     |
| Predict   | `protocol`、`rows`、`date_range`   | `output_columns=[]`、`statistics={}`     |
| Portfolio | `portfolios`、`protocol`           | 明文组合身份与冻结的信号产物             |
| Backtest  | `portfolios`、`protocol`           | 共享的 `artifacts={}`                    |

训练索引直接读取 Task metadata。

所有类型继承 `BaseOutputParams`；额外字段需通过输出子类声明，否则 `extra=forbid` 校验失败。`date_range` 是字符串映射，页面按 `start` 与 `end` 取值，生产者应采用这些 key。

训练在有序 `output_params.model_groups` 中声明模型组。每组持有 `train_start`、`train_end_exclusive`、`use_from` 和可选的右开边界 `use_to`，组内 `models` 保存成员配置、状态、产物与曲线。各组按时间排序且不重叠；选择要求所需成员已完成、日期范围完整覆盖。预测分数映射仅保存在 `protocol.score_columns`，数据通过 `artifacts.predictions` 注册。单成员生产者使用相同集合契约。股票插件在调用回测账本前选择或聚合原始分数，`pred` 表示最终选股分数。

成员数量用于区分单成员和多成员输出，不表示预测目标数量：单个模型可以包含多个目标，多个模型也可以预测同一个目标。

## ETL 产物

ETL 生产者在 `metadata.json.output_params.protocol` 扩展中描述特征语义、来源和质量。产物角色与文件名由生产者契约定义，消费者通过发布记录解析文件，不假定其他插件的目录布局。将外部生成的文件复制进 Task 目录时，保留稳定文件名并发布任务内的产物记录。

基类保存输出文件描述和列名。qlib_a158 扩展 feature_count、symbols、schema、protocol、market_state 等信息，生成：

| artifact 名  | 文件                 | 用途                               |
| ------------ | -------------------- | ---------------------------------- |
| `dataset`    | `alpha158.parquet`   | 训练、因子分析和预测的源数据       |
| `statistics` | `alpha158_stats.csv` | 各列质量统计                       |
| `labels`     | `labels.parquet`     | 固定次一市场日原始收益及可用状态   |
| `market`     | `market.parquet`     | 报价、复权因子、成交资格及行情状态 |
| `calendar`   | `calendar.parquet`   | 独立于预测资格的市场日期           |

所有下游通过任务内相对路径 `artifacts` 注册表读取文件。ETL、分析、预测和训练输出注册任务内相对路径。

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

qlib_a158 实际生成 `factor_analysis_stats.csv`、`factor_quantiles_stats.csv`，映射名分别为 `result`、`quantiles`，并保存 definitions、labels 等扩展字段。

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

qlib_a158 把 L2 放左轴、L1 放右轴；曲线是直接保存在模型 metadata 中的调参模型训练/验证历史。`model` 与 `feature_importance` 分别引用最终模型及 `feature_importance_stats.csv`。

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

Predict 产出完整预测横截面；`BaseStockPortfolioTask` 使用信号时点信息构建组合，`BaseStockBacktestTask` 消费 Portfolio Task 的产物并独立加载行情、日历与可选标签。组合构建不读取未来收益。

Portfolio 原位读取 Predict 的原始打分和信号辅助字段。每个 Task 仅发布一份 `rankings.parquet`，以 `universe_key`、`trade_date`、`trade_time`、`ts_code`、`target_rank` 保存各股票池全部合格候选的排名。`score_column` 引用未改变的上游分数列；实际聚合打分时才新增一份仅含主键和最终 `pred` 的 `scores.parquet`。`universes` 将排名 key 映射到股票池定义。不同 N、策略共用这些文件。候选标记由排名是否存在恢复，目标按 `target_rank <= top_n` 派生，权重为 `1/top_n`，空缺份额留现金。

```bash
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<Predict Task ID>"]' --top-ns '[5,10,30]' --holding-days 1
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<Portfolio Task ID>"]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

`strategies` 可提供多个策略定义，组合按股票池 × 策略 × Top N 展开，省略时使用 Task 默认策略。`output_params.portfolios` 保存明文身份与共享排名、可选聚合分数的引用，不按组合序号保存信号或目标表。

## 回测 dimensions 与 protocol

Portfolio 输出使用列表，每项以明文 `portfolio_id` dict 声明语义身份。不同生产者可以增加字段；相同语义复用 `universe`、`score_selection`、`strategy`、`top_n`、`allocation`、`trade_time`。字段顺序不影响身份，重复组合被拒绝。跨 Task 使用 Task ID 与明文身份定位。

```json
{
  "signals_format": "stock-signals-v3",
  "portfolios": [
    {
      "portfolio_id": {
        "universe": {
          "kind": "all"
        },
        "score_selection": {
          "method": "model"
        },
        "strategy": {
          "kind": "fixed_expiry",
          "holding_days": 1
        },
        "top_n": 5,
        "allocation": "equal_slot",
        "trade_time": "1500"
      },
      "artifacts": {
        "rankings": "rankings"
      }
    }
  ],
  "protocol": {
    "version": 1,
    "task_type": "portfolio",
    "market_upstream_task_id": "etl#qlib_a158_etl#data"
  },
  "artifacts": {
    "rankings": {
      "path": "rankings.parquet",
      "size": 100,
      "revision": "100:1"
    }
  },
  "score_column": "pred",
  "universes": [
    {
      "key": "all",
      "label": "All market",
      "parameters": {
        "kind": "all"
      }
    }
  ]
}
```

Backtest 输入的 `upstream_task_ids` 必须包含 Portfolio Task，可额外指定 ETL；`portfolio_ids` 可选择身份子集。费用、行情缺失策略、截止日期、年化参数与基准覆盖率属于 Backtest。结果保留 `portfolios` 列表，每项增加 `dimensions`、`date_range`、`days`、`evaluation_status`，并引用 `daily`、`summary`、`orders`、`positions`、`trades`。文件写入 `portfolios/<序号>/`；序号只用于存储。

插件的组合 Task 覆盖 `build_universes()`、`select_universe()`、`prepare_signals()` 和 `strategy()`。评价扩展使用 Backtest 的 `evaluation_files()` 与 `evaluate()`，让离线和在线调用共用政策资源与核算。目标代表意图；实际成交受现金、持仓与市场约束，有状态策略在账本中读取实际持仓。

## 统一回测信号

组合与在线报告声明 `stock-signals-v3`。`PortfolioReader` 从引用的预测、最终分数和冻结排名恢复完整信号，读取时校验 `input_sources` 中的上游执行批次与文件修订，拒绝已替换的预测。Backtest 从 ETL 读取标签，仅发布账本与评估结果。在线提交保留本次预测、排名与可选聚合分数；连续信号从每日提交重建，不保存累计信号副本。Studio 与比较任务沿用相同分工。

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

## 窗口任务与在线历史

回测插件通过 `evaluation_files(params)` 声明政策资源，通过 `evaluate(signals, market, calendar, labels, identity, params, *, as_of_date, files)` 复用评价实现。普通 Backtest Task 与在线、比较流程调用同一方法；`identity` 提供已发布的策略与 Top N，调用方在评价前固定声明文件的修订。

`BaseWindowTask` 接收有序 `ExecutionWindow`，起止时间必须带时区；逐窗口发布 `WindowResult`，状态为 `done`、`skipped`、`incomplete` 或 `failed`。这些是业务结果，与 Task 生命周期状态分开。`BaseRealtimeApiTask` 轮询 `collect()`，`BaseInferenceTask` 在整次执行中固定非空模型身份。网络调用与重试应以 `DeadlineBudget.remaining_seconds` 限制。

`publish_online()` 将已完成的推理结果写入 Task 普通的 `outputs/<HHMM>/` 目录，返回包含来源执行、模型身份、协议及注册文件的 `OnlineCommit`。执行器通过 `persistent/task.lock` 独占执行，每次结束向 `persistent/history.jsonl` 追加一行终态元信息 JSON。在线业务文件使用普通 Task 输出目录。

在线报告通过 `StockOnlineReport` 和 `OnlineCommit` 声明生产执行、模型、协议及产物，具体目录布局和快照归属由生产者决定。股票报告中的 `protocol.report.portfolios` 将稳定组合键映射到完整身份，账本用 `portfolio_key` 区分组合：positions 描述当前持仓，orders/trades 描述事件，daily 每个组合每天一行，summary 保存截至评价日的统计。Studio 可按这些契约拼接日期快照。引用子任务证据时必须固定子执行和文件修订，已替换的证据不能用新执行代替。

均值或排名均值集成的组合键不包含滚动变化的 seed 成员，每日完整身份仍保留实际成员；显式选择不同 seed 的组合使用不同键。

## 生产者验收

1. 用实际输出子类验证 output_params。
2. 先写文件，再调用 artifact_record 并发布 metadata。
3. 用 `verify_artifact` 解析并核验注册产物，消费上游时记录并核验来源执行和文件修订。
4. 对照当前 Studio 字段检查日期、数值单位、布尔列和结构数组。
5. 验证曲线与下游契约，保留 protocol 的明确执行说明。

不要手工用占位摘要冒充真实文件；也不要修改 metadata 来掩盖失败执行。所有图表依赖相应生产者和读取端的共同契约。

## Studio 传输契约

Studio 保存任务记录及其 `output_params`。研究和比较页面复用索引查询，先过滤再复制结果。在线报告设置仅保存在 `report.commit.protocol.report`。Agent 历史接口只返回展示块，原始 transcript 仍由会话存储持有。修改 Python 传输契约后，在 `axonx_studio/` 执行 `npm run contracts:generate` 和 `npm run contracts:check`。

## 实现依据

- [`基础研究模型`](../../../axonx/task/models/)
- [`产物 helper`](../../../axonx/task/storage/artifacts.py)
- [`Studio 读取映射`](../../../axonx_studio/src/features/research/ResearchPage.tsx)
- [`回测展示类型`](../../../axonx_studio/src/features/research/backtest/types.ts)
- [`qlib_a158 输出实现`](../../../plugins/qlib_a158/axonx_qlib_a158/)
