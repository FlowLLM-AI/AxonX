---
title: 实验设计与独立确认
description: 固定控制变量、执行消融、锁定方案，并用独立窗口评估研究证据。
---

# 实验设计与独立确认

AxonX 保存执行证据，实验设计决定这些证据能支持什么结论。本页说明如何把一次参数或特征修改组织为可检查的研究比较；具体算法由插件 README 维护，本次结果集中在本页。

![筛选、配置锁定与独立确认](../../figures/research/experiments.svg)

## 先定义问题与控制变量

执行前记录研究假设、基线、候选方案、选择规则和评估窗口。比较特征方案时固定数据快照、标签、样本过滤、训练参数和回测假设；比较成本或组合管理时固定兼容的预测产物。

| 要记录的内容       | 核对方式                                                 |
| ------------------ | -------------------------------------------------------- |
| 执行服务与插件版本 | 保存目标地址、服务版本、插件版本或源码版本               |
| 数据快照与时点     | 保存来源、覆盖日期、分区及校验信息；确认信号何时可用     |
| 样本与模型         | 保存标签、过滤规则、训练与验证窗口、超参数和随机种子     |
| 执行与成本         | 保存股票池、成交代理、延迟退出、成本率、年化与无风险设置 |
| 选择规则           | 事先确定候选集、主要指标、约束和并列时的处理             |
| 实验证据           | 保存 Task/运行标识、输入、metadata、日志和关键产物       |

固定随机种子不能替代固定数据和依赖环境。字段时点必须符合预测时可用信息，不能用未来标签或未来可交易性构建特征。

## 分开训练、筛选与确认

1. **训练与验证**：在训练窗口内选择模型参数或早停轮数。
2. **筛选**：在预先指定的样本外窗口比较候选方案，按事先规则选择。
3. **锁定**：记录选择理由、特征组、模型参数与执行协议。
4. **独立确认**：只比较基线与锁定方案；不根据这个窗口的结果继续选组或调参。

用于选择方案的窗口不能同时作为独立确认。若看到确认结果后继续修改，需将该窗口视为开发信息，为新方案重新建立确认设计。

本文实验固定 risk 因子和 3 日策略，训练区间为 `[20150101,20230101)`，从 2023 年起评估，尚无独立确认窗口。三组结果见下文。

## 用 Task 保存消融链

优先复用兼容的上游数据，让每个候选方案拥有独立的 Train、Predict 和 Backtest 身份。每次提交保存真实返回的 Task/Run ID，等待成功后再提交下游。框架记录血缘，但不自动运行整条 DAG。

```text
共同 ETL
  ├─ 基线 Train → 筛选 Predict → 筛选 Backtest
  └─ 候选 Train → 筛选 Predict → 筛选 Backtest
锁定方案后
  ├─ 基线 Train → 确认 Predict → 确认 Backtest
  └─ 锁定 Train → 确认 Predict → 确认 Backtest
```

使用默认生成名称或不同的显式名称；同名重跑会替换终态目录。失败和作废运行也应保留原因，不只汇报成功结果。命令与等待方法见[研究流程](workflow.md)，增强插件的分组消融命令见[复现实验](../../../plugins/qlib_factor/README_ZH.md#安装与执行)。

## 比较共同窗口与相同口径

先核对双方协议、数据、日期、Top N、成本和年化参数，再比较收益与风险。Studio [策略比较](strategy-comparison.md)可以对齐共同有效日期并重算指标；日期对齐不自动保证研究设置相同。

信号质量与组合收益应分别报告：RankIC 衡量排序相关性；净收益、回撤与 Sharpe 还受成本和成交、退出假设影响。某一个 Top N 改善不能推导所有组合规模都改善。

[回测解读](backtest.md)区分插件汇总、前端窗口重算、毛收益与净收益。实验额外计算的净夏普比率 应明确公式与数据来源，不能直接用原产物的 gross Sharpe 代替。

## 解释增量与不确定性

同一日期上的基线与增强方案可构成配对差值。报告点估计时，同时说明有效样本、缺失日期和时间相关性处理。区块 bootstrap 的统计对象、区块长度、次数与随机种子都应记录。

循环区块 bootstrap 可用于每日 RankIC 或净收益的配对差值；应记录区块长度、重采样次数和种子，并区别每日均值差与年化复利收益差。本次三版本对照报告点估计、选择依据及数据质量限制。

这种计算属于实验分析，Studio 策略比较页面不会自动生成上述 bootstrap 检验。原始日级产物、对齐方法与计算记录需要在实验环境保留。

## 阅读 Agent 开发的增强案例

[README 开发流程](../../../README_ZH.md#agent-接入与开发指南)介绍 Skill + Prompt 驱动的插件开发；[项目 Benchmark](../../../README_ZH.md#benchmark-agent-开发市场横截面增强特征)展示 Alpha158 增强案例。[Qlib Factor](../../../plugins/qlib_factor/README_ZH.md)介绍特征定义、任务参数和执行命令。

三组实验的共同设定与完整指标见[实验对比](#comparison)；各插件 README 只介绍算法与配置。原始日志、metadata 与日级产物留在执行工作区。

## 报告结论

报告基线与锁定方案、选择过程、独立窗口、指标变化和不确定性；列出失败记录、下降的指标及交易假设限制。任务成功说明执行完成，研究结论仍需由这些证据支持。

<a id="comparison"></a>

## 三组实验

本页只保留 2026-10-10 在 45 机器用提交 `8fc1174` 完成的一组实验：Alpha158、risk 因子、3 日排名保留策略。两条模型流程从同一数据快照重跑 ETL、训练、预测和回测；策略复用本次因子模型预测。买入费用 0.05%，卖出费用 0.15%，其他参数保持原设定。算法与参数接口见各插件 README。

### 共同设定

| 设定          | 值                                                                                                                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数据 / 股票池 | Tushare；沪深市场，排除北交所； 11,446,950 行，5,477 只股票；158 / 171 ETL 特征； min_history_coverage=0.8.                                                                               |
| 训练 / 标签   | [20150101,20230101); label_return_rank; trim_tail=0.025; label_winsorize_tail=0.025; validation_ratio=0.10; 剔除跨训练截止日的标签。                                                      |
| 样本 / 验证   | refit=5,838,557; tuning=5,010,901; validation=823,601; validation_start=20220316                                                                                                          |
| 模型          | parameter_preset=axonx; learning_rate=0.03; num_leaves=31; max_depth=-1; min_data_in_leaf=20; bagging_fraction=0.9; bagging_freq=1; lambda_l1=lambda_l2=0; random_seed=42; num_threads=8. |
| 训练轮数      | num_boost_round=1000; early_stopping_rounds=50; 按验证 L2 选轮数，再重拟合全部训练样本。                                                                                                  |
| 预测 / 回测   | pred_start=20230101; pred_end=20261008; as_of_date=20261008; 909 个市场日； top_ns=[20,30]; index_codes=[]; minimum_index_weight_coverage=0.98.                                           |
| 费用 / 年化   | buy_cost_rate=0.0005; sell_cost_rate=0.0015; 不设最低金额费用; annualization_days=252; annual_risk_free_rate=0.012.                                                                       |
| 成交          | 同收盘报价代理；先卖后买；未成交目标不补位；不强制期末清仓；共用基础 ETL 行情、日历和标签。                                                                                               |

### 方案设定

| 方案     | 特征 | context_groups | feature_fraction | 选定轮数 | 验证 RankIC |                   退出 |
| -------- | ---: | -------------: | ---------------: | -------: | ----------: | ---------------------: |
| Alpha158 |  158 |              — |              0.9 |      422 |     0.10789 |         holding_days=1 |
| 风险因子 |  160 |           risk |              1.0 |      426 |     0.11321 |         holding_days=1 |
| 3 日策略 |  160 |           risk |              1.0 |      426 |     0.11321 | minimum_holding_days=3 |

策略使用 `replacement_fraction=0.2`、`rank_buffer=1`，Top20/Top30 每日每侧最多成交 4/6 只，首次建仓豁免。因子只选择两个 risk 特征；`context_windows=[10]` 不改变 risk 组的固定窗口。

### 指标口径

IC/RankIC 为信号日合格股票预测与有效次日标签的每日 Pearson/Spearman 相关均值；RankICIR 使用日 RankIC 的均值除以样本标准差，再乘 sqrt(252)。净年化为复利净收益按 252 日年化；净夏普比率扣除日化无风险收益，波动率使用样本标准差。回撤峰值包含初始权益 1；换手与费用按前日权益归一化。

市场均值是有效前向标签股票的等权收益；HS300 是权重覆盖至少 98% 的成分加权代理。净超额为组合净日收益减基准日收益；净 IR 为其均值/样本标准差 × sqrt(252)，净超额年化与回撤使用超额复利曲线。超额指标仅用共同基准有效日期。

![基线与风险因子的信号质量](../../figures/benchmark/qlib-signal-quality.svg)

![三组实验的净年化收益](../../figures/benchmark/qlib-topn-results.svg)

### 整体信号与 Top20

| 指标                              | Alpha158 | 风险因子 | 3 日策略 |
| --------------------------------- | -------: | -------: | -------: |
| 整体信息系数（IC）                |   0.0530 |   0.0545 |   0.0545 |
| 整体秩信息系数（RankIC）          |   0.0923 |   0.0966 |   0.0966 |
| 整体秩信息比率（RankICIR，年化）  |  12.8817 |  14.2859 |  14.2859 |
| 净年化收益                        |    7.67% |    9.03% |   32.37% |
| 净累计收益                        |   30.56% |   36.60% |  174.99% |
| 净夏普比率                        |   0.3619 |   0.4052 |   1.1575 |
| 净年化波动率                      |   28.20% |   28.53% |   26.19% |
| 最大回撤                          |  -38.65% |  -40.69% |  -24.91% |
| 日收益胜率                        |   53.47% |   53.47% |   55.89% |
| 日均双边换手                      |  198.83% |  199.35% |   40.01% |
| 日均费用 / 前日权益               |  0.1989% |  0.1994% |  0.0400% |
| 已完成交易                        |   18,032 |   18,079 |    3,624 |
| 相对市场均值的净超额年化收益      |   -3.50% |   -1.88% |   18.64% |
| 相对市场均值的净信息比率          |  -0.1422 |  -0.0665 |   1.4543 |
| 相对市场均值的净超额最大回撤      |  -28.51% |  -21.71% |  -18.63% |
| 相对沪深 300 代理的净超额年化收益 |    2.74% |    4.07% |   26.04% |
| 相对沪深 300 代理的净信息比率     |   0.2340 |   0.2936 |   1.2697 |
| 相对沪深 300 代理的净超额最大回撤 |  -31.94% |  -29.37% |  -23.96% |

### Top30

| 方案     | 净年化 | 净夏普 | 最大回撤 |    换手 | 净 IR：市场均值 | 净 IR：HS300 |
| -------- | -----: | -----: | -------: | ------: | --------------: | -----------: |
| Alpha158 |  0.97% | 0.1308 |  -40.60% | 199.02% |         -0.5956 |      -0.0792 |
| 风险因子 |  4.25% | 0.2472 |  -41.41% | 199.37% |         -0.4265 |       0.0822 |
| 3 日策略 | 29.30% | 1.0884 |  -25.53% |  40.03% |          1.4081 |       1.1909 |

### Top20 分年净年化

| 年份 | 交易日 | Alpha158 | 风险因子 | 3 日策略 |
| ---- | -----: | -------: | -------: | -------: |
| 2023 |    242 |   -9.13% |  -10.06% |    9.71% |
| 2024 |    242 |    5.06% |   10.52% |   17.73% |
| 2025 |    243 |   48.57% |   56.63% |   72.52% |
| 2026 |    182 |   -9.31% |  -14.73% |   39.42% |

### 结果限制

本次只运行既定三组配置，没有重新筛选候选，也没有独立确认窗口。基础/因子模型的 feature_fraction 为 0.9/1.0，差异不能单独归因于新增因子。2026 为不完整年度；成交使用同收盘报价代理。三个回测状态均为 `incomplete_market_data`，缺行情可能延迟退出并保留旧估值。

### 复现

固定同一份数据快照，每次提交后保存 Task/Run ID，等待成功再提交下游。远程命令使用同一 `--target`。固定持有回测分别对基础与因子预测执行一次；基础版使用 `qlib_a158_backtest`。

```bash
# 基础模型：158 个特征
axonx submit --task qlib_a158_etl --input-dir '<same_data_snapshot>' --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<base_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<base_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# 因子模型：158 个基础特征加两个风险因子
axonx submit --task qlib_factor_etl --input-dir '<same_data_snapshot>' --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<factor_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --context-groups risk --context-windows '[10]' \
  --feature-fraction 1.0 --random-seed 42 --num-threads 8
axonx submit --task qlib_factor_predict --source-tasks '<factor_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# 固定持有：分别对基础和因子预测执行一次
axonx submit --task qlib_factor_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'

# 策略版本：复用因子预测，采用选中的 3 日策略
axonx submit --task qlib_strategy_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'
```

### 任务来源

执行工作区：45 机器 `/nas/jinli.yl/data/axon`；原始产物保存在该工作区。仅列本次实验记录。

| 阶段              | Task ID                                                       | Run ID                             |
| ----------------- | ------------------------------------------------------------- | ---------------------------------- |
| base_etl          | `etl#qlib_a158_etl#fees-1010-base-etl`                        | `41fb603467ac4e78acc68294ae7d2699` |
| base_train        | `train#qlib_a158_train#fees-1010-base-train`                  | `eff2152ad9a244cb95a91f834e41a33a` |
| base_predict      | `predict#qlib_a158_predict#fees-1010-base-predict`            | `c9eaa50835004b9284897e5f2ad001e6` |
| base_backtest     | `backtest#qlib_a158_backtest#fees-1010-base-backtest`         | `b7ca108ed67a4ef4b38968f0770430bc` |
| factor_etl        | `etl#qlib_factor_etl#fees-1010-factor-etl`                    | `1d17d053b24b4e58b2175184372ea718` |
| factor_train      | `train#qlib_factor_train#fees-1010-factor-train`              | `c3ec05d4cbac4905b5603d9d6d2b07b1` |
| factor_predict    | `predict#qlib_factor_predict#fees-1010-factor-predict`        | `f541bb3b20eb406fb9dfb5c9c4f705a4` |
| factor_backtest   | `backtest#qlib_factor_backtest#fees-1010-factor-backtest`     | `3d0a9f5a718a4bb4a6f14873cad8e8ad` |
| strategy_backtest | `backtest#qlib_strategy_backtest#fees-1010-strategy-backtest` | `51c8cf5fca3d47cf95c6f4965e0c0302` |

| 共同输入 |                                                            SHA-256 |
| -------- | -----------------------------------------------------------------: |
| market   | `5416cdf28fdd8bfb0280afa5d080fd7db0c6e50b82373cd024e910229c8dbc17` |
| calendar | `b8048084ff1abafa81b97af01a58b7c8addf96fb061b7898127035e61408e731` |
| labels   | `52e832db44e3a961942c7d6e485b355378dea081c8b53ca34cf01aa2b1d0bda6` |

三个回测共用上述输入摘要；因子与策略共用预测摘要。核心/插件版本 0.1.1/0.2.0，Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0。
