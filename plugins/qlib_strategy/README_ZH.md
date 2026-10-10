# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 继承 `qlib_factor` 和 `qlib_a158`，在同一预测上研究持仓策略。框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。关闭固定到期退出，`holding_days=1`，`planned_exit_date` 为空。

## 安装与执行

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx plugin install plugins/qlib_strategy --target http://research.example:1024
axonx submit --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

可复用成功的基础或增强预测。提交后保存 Task / Run ID，等待成功再读取结果。上游 `qlib_strategy_etl`、`qlib_strategy_analysis`、`qlib_strategy_train`、`qlib_strategy_predict` 注册因子层实现；策略比较直接复用已有预测。通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更仍要求重启；核心与插件使用同一源码仓库版本。

<a id="experiments"></a>

## 最终实验设定与结果

本节记录本插件的最终实验；跨插件对比见[三个版本实验对比](../../docs/zh/research/experiments.md#comparison)。指标整理自 45 机器成功任务的 metadata、summary.parquet、daily.parquet 和 trades.parquet，原始产物保留在执行工作区。

### 本版本配置

复用因子版模型预测；minimum_holding_days=3、replacement_fraction=0.2、rank_buffer=1；无需重新训练。

数据、训练窗口、样本过滤、成交与费用共同设定见[三个版本实验对比](../../docs/zh/research/experiments.md#comparison)。

本次模型使用 160 个特征，早停选择 426 轮后全训练期重拟合，内部验证 RankIC 为 0.11321。

固定上游 stock_risk 预测 `predict#qlib_factor_predict#2026100917Z7Ys`；因子定义见 [Qlib Factor](../qlib_factor/README_ZH.md#experiments)。策略版使用 3 日最短持有期，按上文排名保留规则执行；Top20／Top30 每日每侧成交数量上限为 4／6 只。

3 日方案在已有候选中净年化、净夏普比率 和回撤表现更好，因此为文档唯一展示的策略版本；这是重复开发窗口的探索筛选，尚未独立确认。默认最短持有期仍为 10 日，复现本文结果必须显式传入 3。

### 指标口径

信息系数／秩信息系数、净收益、夏普比率、换手与基准超额的统一定义见[实验对比](../../docs/zh/research/experiments.md#comparison)。组合指标使用 909 日；基准超额使用共同有效的 908 日。

### 整体信号与 Top20 完整结果

| 指标                              | 3 日策略 |
| --------------------------------- | -------: |
| 整体信息系数（IC）                |   0.0545 |
| 整体秩信息系数（RankIC）          |   0.0966 |
| 整体秩信息比率（RankICIR，年化）  |  14.2859 |
| 净年化收益                        |   32.36% |
| 净累计收益                        |  174.92% |
| 净夏普比率                        |   1.1571 |
| 净年化波动率                      |   26.19% |
| 最大回撤                          |  -24.91% |
| 日收益胜率                        |   55.89% |
| 日均双边换手                      |   40.02% |
| 日均费用 / 前日权益               |  0.0400% |
| 已完成交易                        |    3,624 |
| 相对市场均值的净超额年化收益      |   18.65% |
| 相对市场均值的净信息比率          |   1.4547 |
| 相对市场均值的净超额最大回撤      |  -18.63% |
| 相对沪深 300 代理的净超额年化收益 |   26.04% |
| 相对沪深 300 代理的净信息比率     |   1.2699 |
| 相对沪深 300 代理的净超额最大回撤 |  -23.96% |

### Top30 结果

| 方案     | 净年化收益 | 净夏普比率 | 最大回撤 | 日均双边换手 | 相对市场均值的净信息比率 | 相对沪深 300 代理的净信息比率 |
| -------- | ---------: | ---------: | -------: | -----------: | -----------------------: | ----------------------------: |
| 3 日策略 |     29.29% |     1.0880 |  -25.53% |       40.03% |                   1.4086 |                        1.1912 |

### Top20 分年结果

| 年份 | 交易日数 | 3 日策略 |
| ---- | -------: | -------: |
| 2023 |      242 |    9.65% |
| 2024 |      242 |   17.73% |
| 2025 |      243 |   72.54% |
| 2026 |      182 |   39.43% |

各年值为对应区间净年化；2026 年截至 10 月 8 日。结果为 `incomplete_market_data`，缺报价可能延迟退出并沿用旧估值，同收盘成交为代理假设。3 日方案是在重复开发窗口筛出的探索候选，不构成独立确认，默认仍为 10 日。

### 复现实验

每阶段保存返回的 Task/Run ID 并等待成功后再提交下游；远程执行时统一使用同一 `--target`。以下参数与 实验设定一致，其余默认值提交前用 `get_task_definition` 核对。

```bash
axonx submit --task qlib_strategy_backtest --source-tasks '<stock_risk_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### 任务来源与输入校验

执行工作区：45 机器 `/nas/jinli.yl/data/axon`。

| 阶段／方案   | 任务标识                                         | 运行标识                           |
| ------------ | ------------------------------------------------ | ---------------------------------- |
| 3 日策略回测 | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |

| 输入     | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

框架/插件版本为 0.1.1 / 0.2.0；Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0。新数据不保证重现未发布的历史快照；原始运行产物不随仓库提交。
