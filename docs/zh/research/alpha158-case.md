# Alpha158 改进实验

本案例比较适配后的 Qlib Alpha158 基线、两个新增风险因子与排名保留策略。控制变量与独立确认方法见[实验设计](experiments.md)。

本页只保留 2026-10-10 在 45 机器用提交 `8fc1174` 完成的一组实验：Alpha158、risk 因子、3 日排名保留策略。两条模型流程从同一数据快照重跑 ETL、训练、预测和回测；策略复用本次因子模型预测。买入费用 0.05%，卖出费用 0.15%，其他参数保持原设定。算法与参数接口见各插件 README。

## 共同设定

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

## 方案设定

| 方案     | 特征 | context_groups | feature_fraction | 选定轮数 | 验证 RankIC |                   退出 |
| -------- | ---: | -------------: | ---------------: | -------: | ----------: | ---------------------: |
| Alpha158 |  158 |              — |              0.9 |      422 |     0.10789 |         holding_days=1 |
| 风险因子 |  160 |           risk |              1.0 |      426 |     0.11321 |         holding_days=1 |
| 3 日策略 |  160 |           risk |              1.0 |      426 |     0.11321 | minimum_holding_days=3 |

策略使用 `replacement_fraction=0.2`、`rank_buffer=1`，Top20/Top30 每日每侧最多成交 4/6 只，首次建仓豁免。因子只选择两个 risk 特征；`context_windows=[10]` 不改变 risk 组的固定窗口。

## 指标口径

IC/RankIC 为信号日合格股票预测与有效次日标签的每日 Pearson/Spearman 相关均值；RankICIR 使用日 RankIC 的均值除以样本标准差，再乘 sqrt(252)。净年化为复利净收益按 252 日年化；净夏普比率扣除日化无风险收益，波动率使用样本标准差。回撤峰值包含初始权益 1；换手与费用按前日权益归一化。

市场均值是有效前向标签股票的等权收益；HS300 是权重覆盖至少 98% 的成分加权代理。净超额为组合净日收益减基准日收益；净 IR 为其均值/样本标准差 × sqrt(252)，净超额年化与回撤使用超额复利曲线。超额指标仅用共同基准有效日期。

![基线与风险因子的信号质量](../../figures/benchmark/qlib-signal-quality.svg)

![三组实验的净年化收益](../../figures/benchmark/qlib-topn-results.svg)

## 整体信号与 Top20

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

## Top30

| 方案     | 净年化 | 净夏普 | 最大回撤 |    换手 | 净 IR：市场均值 | 净 IR：HS300 |
| -------- | -----: | -----: | -------: | ------: | --------------: | -----------: |
| Alpha158 |  0.97% | 0.1308 |  -40.60% | 199.02% |         -0.5956 |      -0.0792 |
| 风险因子 |  4.25% | 0.2472 |  -41.41% | 199.37% |         -0.4265 |       0.0822 |
| 3 日策略 | 29.30% | 1.0884 |  -25.53% |  40.03% |          1.4081 |       1.1909 |

## Top20 分年净年化

| 年份 | 交易日 | Alpha158 | 风险因子 | 3 日策略 |
| ---- | -----: | -------: | -------: | -------: |
| 2023 |    242 |   -9.13% |  -10.06% |    9.71% |
| 2024 |    242 |    5.06% |   10.52% |   17.73% |
| 2025 |    243 |   48.57% |   56.63% |   72.52% |
| 2026 |    182 |   -9.31% |  -14.73% |   39.42% |

## 结果限制

本次只运行既定三组配置，没有重新筛选候选，也没有独立确认窗口。基础/因子模型的 feature_fraction 为 0.9/1.0，差异不能单独归因于新增因子。2026 为不完整年度；成交使用同收盘报价代理。三个回测状态均为 `incomplete_market_data`，缺行情可能延迟退出并保留旧估值。

这些结果比较的是 AxonX 插件配置，不能据此认定优于原始 Qlib 基准。数据、标签、训练与交易协议存在差异，详见[与原始 Qlib 的差异](../../../plugins/qlib_a158/README_ZH.md#与原始-qlib-的差异)。

## 复现

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

## 任务来源

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
