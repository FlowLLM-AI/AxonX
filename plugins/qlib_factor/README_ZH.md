# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 在 `qlib_a158` 的 158 个基础特征上，增加两类全局因子：最近 1/3/5/10 个交易日股票收益的截面均值与方差，共 8 列；另外发布 5 个个股中性动量/风险特征，ETL 共 13 个增强列、171 个特征。

训练继承基础插件的截止日隔离、末尾 10% 日期早停与全训练期重拟合。预测和普通回测复用基础插件。

## 因子与时点

| Group    | Features | 定义                                         |
| -------- | -------: | -------------------------------------------- |
| mean     |        4 | 各窗口收益截面缩尾均值，反映市场整体涨跌方向 |
| variance |        4 | 各窗口收益截面缩尾样本方差，反映股票涨跌分歧 |
| neutral  |        3 | 5/10/20 日 beta 调整动量                     |
| risk     |        2 | 20 日特质波动与下行风险                      |

每只股票收益为复权 C(T)/C(T−h)−1，h=1/3/5/10 个市场交易日。两个端点须有报价且成交量、成交额和复权价格为正；包含涨跌停股票，不使用未来标签或可交易性筛选。各日期、各窗口独立用 2%/98% 线性分位缩尾，参考 Axon2 的全局特征实现，再计算等权均值与样本方差（ddof=1）。空股票池保留缺失，单股票方差缺失。方差描述截面分歧；均值接近零并不能单独证明多数股票震荡。

因子在 T 收盘后可用，同一日所有股票共享相同值，不能用单因子截面 IC 判断，应比较模型消融。定义见 [cross_section.py](axonx_qlib_factor/internal/cross_section.py)；ETL 保存各窗口样本数和每日因子值。

`context_groups` 接受逗号分隔的 `mean`、`variance`、`neutral`、`risk`，或 `none`。默认暂为 `none`，待对照验证后再选择增强方案。兼容性变更：旧 `market/liquidity/relative/interaction` 组全部撤回，旧列从新模型中排除；旧配置组名会明确报错，历史任务不改写。使用新组须重新运行 ETL。

`context_windows` 可选择 `[1,3,5,10]` 的非空子集，默认全部四个窗口。ETL 发布全部 13 列，context_windows 只过滤全局均值/方差；个股组使用固定窗口。消融复用同一数据集，训练协议记录实际窗口。例如 `--context-groups mean,variance --context-windows '[10]'` 只加入两个 10 日因子。

个股动量与风险的计算要求及最终 risk 实验见下文[详细实验设定](#experiments)。

## 安装与执行

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx get_task_definition --task qlib_factor_train --target http://research.example:1024

axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx --target http://research.example:1024
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

每次保存返回的 Task ID 和 Run ID，等待 `succeeded` 后再提交下游。`qlib_factor_analysis` 是可选的因子分析分支。使用此源码仓库的核心时，通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更，以及不支持插件导入刷新的旧核心仍要求重启。基础数据准备、标签与成交口径见 [Qlib Alpha158](../qlib_a158/README_ZH.md)。

<a id="experiments"></a>

## 最终实验设定与结果

本节记录本插件的最终实验；跨插件对比见[三层实验对比](../../docs/zh/research/experiments.md#comparison)。指标整理自 45 机器成功任务的 metadata、summary.parquet、daily.parquet 和 trades.parquet，原始产物保留在执行工作区。

### 详细 Setting

| 环节            | 设定                                                                                                                                                                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数据 / 股票池   | Tushare 复权价量；沪深全市场，排除北交所，不限制 CSI300 成分选股。ETL 输出 20150101–20261008，共 11,446,950 行、5,477 只股票；ETL 发布 171 个特征，最终 risk 模型使用 160 列。min_history_coverage=0.8；停牌、缺报价不前向填充。              |
| 训练日期        | `[20150101,20230101)`；信号日与 label_target_date 都早于排他的训练截止日。内部验证从 20220316 开始，按末尾 10% 日期划分。                                                                                                                     |
| 标签 / 样本     | T→次一市场日复权收盘收益；只保留信号日可买、固定一日标签有效且在截止日前可取得的样本。每日原始收益两侧各剔除 2.5%，rank 用平均名次归一化至 [0,1]，单样本为 0.5；拟合与验证分开转换。label_winsorize_tail=0.025；本实验使用 rank，不使用 CSZ。 |
| 样本数量        | 截尾前 6,147,420 行；截尾后全期重拟合 5,838,557 行；调参训练 5,010,901 行、内部验证 823,601 行。                                                                                                                                              |
| LightGBM        | 4.7.0，parameter_preset=axonx，objective=regression，metric=[l2,l1]；learning_rate=0.03，num_leaves=31，max_depth=-1，min_data_in_leaf=20，bagging_fraction=0.9，bagging_freq=1，lambda_l1=lambda_l2=0。feature_fraction=1.0。                |
| 选轮数 / 重拟合 | num_boost_round=1000，early_stopping_rounds=50；以内部验证 L2 选轮数后重拟合全部训练样本；最终 risk 模型按训练内验证 RankIC 选择。                                                                                                            |
| 确定性          | random_seed=42；LightGBM seed、feature_fraction_seed、bagging_seed、data_random_seed 均为 42；num_threads=8，deterministic=true，force_col_wise=true。                                                                                        |
| 样本外          | pred_start=20230101，pred_end=20261008；实际整体评估 20230103–20261008，909 个市场日，2026 为不完整年度。                                                                                                                                     |
| 组合 / 成交     | 重点 Top20，Top30 辅助；收盘报价为成交代理，先卖后买，遵循涨跌停与可交易限制；新仓最多分配 1/N 权益，不能买入不补位，不能卖出继续持仓并占用资金，保留仓位不再平衡；不强制期末清仓。                                                           |
| 费用 / 年化     | transaction_cost_rate=0.001，每次实际成交买卖各 0.1%；buy_cost_rate=sell_cost_rate=null，沿用共用费率，不设最低费用。annualization_days=252，annual_risk_free_rate=0.012。                                                                    |
| 输入对齐        | 本次回测使用上游 ETL 的 market.parquet、calendar.parquet、labels.parquet；as_of_date=20261008，index_codes=[]，minimum_index_weight_coverage=0.98。                                                                                           |

本次模型使用 160 个特征，早停选择 426 轮后全训练期重拟合，内部验证 RankIC 为 0.11321。

最终 stock_risk 只增加 `f_context_residual_vol20`、`f_context_downside_risk20`，不使用全局均值/方差或 neutral 列。`context_windows=[10]` 是该模型保存的训练配置，仅过滤全局因子，因此对 risk 组无影响。个股日收益按当日横截面 2%/98% 线性分位缩尾；市场收益为同截面的缩尾等权均值。beta 使用截至 T−1 的 60 个市场日、至少 30 个有效成对收益，以协方差/市场方差估计并截断至 [−3,3]；市场方差 ≤1e−12 时缺失。残差日收益为个股缩尾收益 − 历史 beta × 市场收益，20 日残差波动用样本标准差（ddof=1）；下行风险为 sqrt(mean(min(缩尾日收益,0)²))。两者要求 20 日内至少 16 个有效值，缺失/未定义保持缺失。

context_groups=risk，context_windows=[10]，固定持有期 holding_days=1；当前插件默认 context_groups 仍为 none。

### 指标口径

整体 IC/RankIC 是信号日可选股票中有效次日标签与预测的每日 Pearson/Spearman 相关系数均值，与持仓 TopN 和策略无关。RankICIR 未年化值为 mean(日 RankIC)/std(日 RankIC,ddof=1)，年化值再乘 sqrt(252)；表中两种均列出，避免与不年化的因子分析口径混淆。

净年化 = (∏(1+r_net))^(252/D)−1；净 Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252)。最大回撤基于复利净权益，峰值包含初始权益 1；换手 = (实际买入金额+卖出金额)/前日权益，全部换仓约 200%。胜率为净日收益大于 0 的比例。

“市场均值”基准是有有效前向标签的预测全截面股票等权平均收益，不是仅 Top20，也不是风险因子计算中的缩尾均值。HS300 为信号中沪深 300 成分权重加权收益的代理，权重覆盖至少 98%；不是官方 CSI300 指数行情。两个基准的有效日期均为 20230104–20261008（908 日），净超额指标只用该共同窗口；组合自身指标用完整 909 日。

扣费日超额 a_t = r_net,t−r_benchmark,t；**Net IR（净信息比率）** = mean(a)/std(a,ddof=1)×sqrt(252)。净超额年化用 ∏(1+a) 复利并按 908 日年化；净超额最大回撤也基于这条超额复利曲线。它们不是两个年化收益相减，也不是组合/基准权益比；原框架 information_ratio 字段用毛收益，本节重新从日级产物计算扣费指标。

### 整体信号与 Top20 完整结果

| 指标                         | Factor: stock_risk |
| ---------------------------- | -----------------: |
| 整体 IC                      |             0.0545 |
| 整体 RankIC                  |             0.0966 |
| 整体 RankICIR（年化）        |            14.2859 |
| 整体 RankICIR（未年化）      |             0.8999 |
| Net annualized               |              9.04% |
| 净累计收益                   |             36.64% |
| Net Sharpe                   |             0.4054 |
| 净年化波动                   |             28.53% |
| 最大回撤                     |            -40.67% |
| 日收益胜率                   |             53.47% |
| 日均双边换手                 |            199.35% |
| 日均费用 / 前日权益          |            0.1993% |
| 已完成交易                   |             18,079 |
| 净超额年化 vs 市场均值       |             -1.86% |
| Net IR vs 市场均值           |            -0.0649 |
| 净超额最大回撤 vs 市场均值   |            -21.71% |
| 净超额年化 vs HS300 代理     |              4.09% |
| Net IR vs HS300 代理         |             0.2947 |
| 净超额最大回撤 vs HS300 代理 |            -29.34% |

### Top30 结果

| Scheme             | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| ------------------ | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Factor: stock_risk |          4.27% |     0.2480 |      -41.41% |  199.37% |          -0.4236 |        0.0840 |

### Top20 分年结果

| Year | Days | Factor: stock_risk |
| ---- | ---: | -----------------: |
| 2023 |  242 |            -10.08% |
| 2024 |  242 |             10.54% |
| 2025 |  243 |             56.68% |
| 2026 |  182 |            -14.73% |

各年值为对应区间净年化；2026 年截至 10 月 8 日。结果为 `incomplete_market_data`，缺报价可能延迟退出并沿用旧估值，同收盘成交为代理假设。

### 复现实验

每阶段保存返回的 Task/Run ID 并等待成功后再提交下游；远程执行时统一使用同一 `--target`。以下参数与 Setting 表一致，其余默认值提交前用 `get_task_definition` 核对。

```bash
axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 1.0 \
  --random-seed 42 --num-threads 8 \
  --context-groups risk --context-windows '[10]'
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### 任务来源与输入校验

执行工作区：45 机器 `/nas/jinli.yl/data/axon`。

| Stage / scheme               | Task ID                                        | Run ID                             |
| ---------------------------- | ---------------------------------------------- | ---------------------------------- |
| stock_risk: train            | `train#qlib_factor_train#2026100917VGxi`       | `d55e035ab9c549ab840770b1e8444f10` |
| stock_risk: predict          | `predict#qlib_factor_predict#2026100917Z7Ys`   | `1a033666806b4e359c6acc11f8b02399` |
| Factor: stock_risk: backtest | `backtest#qlib_factor_backtest#2026100917v6ku` | `37cf5867c5d344da9c4b6a9b56bc6e24` |
| Factor: stock_risk: backtest | `backtest#qlib_factor_backtest#2026100917v6ku` | `37cf5867c5d344da9c4b6a9b56bc6e24` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

框架/插件版本为 0.1.1 / 0.2.0；Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0。新数据不保证重现未发布的历史快照；原始运行产物不随仓库提交。
