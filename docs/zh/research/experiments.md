---
title: 实验设计与独立确认
description: 固定控制变量、执行消融、锁定方案，并用独立窗口评估研究证据。
---

# 实验设计与独立确认

AxonX 保存执行证据，实验设计决定这些证据能支持什么结论。本页说明如何把一次参数或特征修改组织为可检查的研究比较；具体算法和历史实验数值由插件文档维护。

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
| 实验证据           | 保存 Task/Run ID、输入、metadata、日志和关键产物         |

固定随机种子不能替代固定数据和依赖环境。字段时点必须符合预测时可用信息，不能用未来标签或未来可交易性构建特征。

## 分开训练、筛选与确认

1. **训练与验证**：在训练窗口内选择模型参数或早停轮数。
2. **筛选**：在预先指定的样本外窗口比较候选方案，按事先规则选择。
3. **锁定**：记录选择理由、特征组、模型参数与执行协议。
4. **独立确认**：只比较基线与锁定方案；不根据这个窗口的结果继续选组或调参。

用于选择方案的窗口不能同时作为独立确认。若看到确认结果后继续修改，需将该窗口视为开发信息，为新方案重新建立确认设计。

当前 Qlib Factor 固定训练 `[20150101,20230101)`，使用训练期内部验证 RankIC 选择增强组，从 2023 年起报告统一样本外区间。Qlib Strategy 的主方案预先固定，持有期对照单独展示。最终三层对比见下文，各插件仅维护自己的设定与结果。

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

[回测解读](backtest.md)区分插件汇总、前端窗口重算、毛收益与净收益。实验额外计算的净 Sharpe 应明确公式与数据来源，不能直接用原产物的 gross Sharpe 代替。

## 解释增量与不确定性

同一日期上的基线与增强方案可构成配对差值。报告点估计时，同时说明有效样本、缺失日期和时间相关性处理。区块 bootstrap 的统计对象、区块长度、次数与随机种子都应记录。

循环区块 bootstrap 可用于每日 RankIC 或净收益的配对差值；应记录区块长度、重采样次数和种子，并区别每日均值差与年化复利收益差。本次统一三层对照报告点估计、完整候选及数据质量检查。

这种计算属于实验分析，Studio 策略比较页面不会自动生成上述 bootstrap 检验。原始日级产物、对齐方法与计算记录需要在实验环境保留。

## 阅读 Agent 开发的增强案例

[项目 Benchmark](../../../README_ZH.md#benchmark-agent-开发市场横截面增强特征)介绍 Agent 如何开发独立插件并通过 AxonX 执行研究。[Qlib Factor](../../../plugins/qlib_factor/README_ZH.md)维护特征定义、任务参数、结论和复现命令。

跨插件共同设定、完整指标与控制实验统一见[三层实验对比](#comparison)；各插件 README 分别维护自身的详细 Setting 和实验结果。原始日志、metadata 与日级产物留在执行工作区。

## 报告结论

报告基线与锁定方案、选择过程、独立窗口、指标变化和不确定性；列出失败记录、下降的指标及交易假设限制。任务成功说明执行完成，研究结论仍需由这些证据支持。

<a id="comparison"></a>

## 三层实验设定与结果对比

本节集中维护三个插件之间的共同实验设定、最终方案与必要控制。各插件内部只维护自己的详细设定与结果。共同设置只列一次，方案表仅列差异；实验 CSV/JSON、中间候选、历史报告和归档已删除。结果取自 45 机器成功任务的原始 metadata、summary.parquet、daily.parquet 和 trades.parquet，核对日期与输入哈希后整理。没有重新训练或重跑回测；原始运行产物仍留在执行工作区。

### 共同 Setting

| 环节            | 设定                                                                                                                                                                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数据 / 股票池   | Tushare 复权价量；沪深全市场，排除北交所，不限制 CSI300 成分选股。ETL 输出 20150101–20261008，共 11,446,950 行、5,477 只股票；基础 158 列，增强 ETL 171 列。min_history_coverage=0.8；停牌、缺报价不前向填充。                                |
| 训练日期        | `[20150101,20230101)`；信号日与 label_target_date 都早于排他的训练截止日。内部验证从 20220316 开始，按末尾 10% 日期划分。                                                                                                                     |
| 标签 / 样本     | T→次一市场日复权收盘收益；只保留信号日可买、固定一日标签有效且在截止日前可取得的样本。每日原始收益两侧各剔除 2.5%，rank 用平均名次归一化至 [0,1]，单样本为 0.5；拟合与验证分开转换。label_winsorize_tail=0.025；本实验使用 rank，不使用 CSZ。 |
| 样本数量        | 截尾前 6,147,420 行；截尾后全期重拟合 5,838,557 行；调参训练 5,010,901 行、内部验证 823,601 行。                                                                                                                                              |
| LightGBM        | 4.7.0，parameter_preset=axonx，objective=regression，metric=[l2,l1]；learning_rate=0.03，num_leaves=31，max_depth=-1，min_data_in_leaf=20，bagging_fraction=0.9，bagging_freq=1，lambda_l1=lambda_l2=0。feature_fraction 差异见下表。         |
| 选轮数 / 重拟合 | num_boost_round=1000，early_stopping_rounds=50；以内部验证 L2 选轮数后重拟合全部训练样本，最终因子候选按训练内验证 RankIC 选择。                                                                                                              |
| 确定性          | random_seed=42；LightGBM seed、feature_fraction_seed、bagging_seed、data_random_seed 均为 42；num_threads=8，deterministic=true，force_col_wise=true。                                                                                        |
| 样本外          | pred_start=20230101，pred_end=20261008；实际整体评估 20230103–20261008，909 个市场日，2026 为不完整年度。                                                                                                                                     |
| 组合 / 成交     | 重点 Top20，Top30 辅助；收盘报价为成交代理，先卖后买，遵循涨跌停与可交易限制；新仓最多分配 1/N 权益，不能买入不补位，不能卖出继续持仓并占用资金，保留仓位不再平衡；不强制期末清仓。                                                           |
| 费用 / 年化     | transaction_cost_rate=0.001，每次实际成交买卖各 0.1%；buy_cost_rate=sell_cost_rate=null，沿用共用费率，不设最低费用。annualization_days=252，annual_risk_free_rate=0.012。                                                                    |
| 输入对齐        | 六组回测共用基础 ETL 的 market.parquet、calendar.parquet、labels.parquet；as_of_date=20261008，index_codes=[]，minimum_index_weight_coverage=0.98。                                                                                           |

### 最终方案的差异

| Scheme                | context_groups | Features | feature_fraction | Best rounds | Validation RankIC | Exit policy             |
| --------------------- | -------------- | -------: | ---------------: | ----------: | ----------------: | ----------------------- |
| Alpha158              | —              |      158 |              0.9 |         422 |           0.10789 | fixed holding_days=1    |
| Factor: stock_risk    | risk           |      160 |              1.0 |         426 |           0.11321 | fixed holding_days=1    |
| Strategy: 10d         | risk           |      160 |              1.0 |         426 |           0.11321 | minimum_holding_days=10 |
| Strategy: 3d          | risk           |      160 |              1.0 |         426 |           0.11321 | minimum_holding_days=3  |
| Alpha158 + 10d        | —              |      158 |              0.9 |         422 |           0.10789 | minimum_holding_days=10 |
| Matched Alpha158 + 3d | none           |      158 |              1.0 |         397 |           0.10776 | minimum_holding_days=3  |

四组策略回测均为 `replacement_fraction=0.2`、`rank_buffer=1`：持满最短天数后，优先退出 TopN 以外的最差排名；Top20 每日每侧最多成交 4 只，Top30 为 6 只，首次建仓豁免。`holding_days=1` 在排名策略中不触发固定到期退出，planned_exit_date=null；这是数量上限，不是资金换手上限。10 日为预先指定主方案；3 日为探索候选，默认保持 10 日，因子默认仍为 none。

最终 stock_risk 只增加 `f_context_residual_vol20`、`f_context_downside_risk20`，不使用全局均值/方差或 neutral 列。`context_windows=[10]` 是该模型保存的训练配置，仅过滤全局因子，因此对 risk 组无影响。个股日收益按当日横截面 2%/98% 线性分位缩尾；市场收益为同截面的缩尾等权均值。beta 使用截至 T−1 的 60 个市场日、至少 30 个有效成对收益，以协方差/市场方差估计并截断至 [−3,3]；市场方差 ≤1e−12 时缺失。残差日收益为个股缩尾收益 − 历史 beta × 市场收益，20 日残差波动用样本标准差（ddof=1）；下行风险为 sqrt(mean(min(缩尾日收益,0)²))。两者要求 20 日内至少 16 个有效值，缺失/未定义保持缺失。

### 指标口径

整体 IC/RankIC 是信号日可选股票中有效次日标签与预测的每日 Pearson/Spearman 相关系数均值，与持仓 TopN 和策略无关。RankICIR 未年化值为 mean(日 RankIC)/std(日 RankIC,ddof=1)，年化值再乘 sqrt(252)；表中两种均列出，避免与不年化的因子分析口径混淆。

净年化 = (∏(1+r_net))^(252/D)−1；净 Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252)。最大回撤基于复利净权益，峰值包含初始权益 1；换手 = (实际买入金额+卖出金额)/前日权益，全部换仓约 200%。胜率为净日收益大于 0 的比例。

“市场均值”基准是有有效前向标签的预测全截面股票等权平均收益，不是仅 Top20，也不是风险因子计算中的缩尾均值。HS300 为信号中沪深 300 成分权重加权收益的代理，权重覆盖至少 98%；不是官方 CSI300 指数行情。两个基准的有效日期均为 20230104–20261008（908 日），净超额指标只用该共同窗口；组合自身指标用完整 909 日。

扣费日超额 a_t = r_net,t−r_benchmark,t；**Net IR（净信息比率）** = mean(a)/std(a,ddof=1)×sqrt(252)。净超额年化用 ∏(1+a) 复利并按 908 日年化；净超额最大回撤也基于这条超额复利曲线。它们不是两个年化收益相减，也不是组合/基准权益比；原框架 information_ratio 字段用毛收益，本节重新从日级产物计算扣费指标。

### 整体信号与 Top20 完整指标

| 指标                         | Alpha158 | Factor: stock_risk | Strategy: 10d | Strategy: 3d |
| ---------------------------- | -------: | -----------------: | ------------: | -----------: |
| 整体 IC                      |   0.0530 |             0.0545 |        0.0545 |       0.0545 |
| 整体 RankIC                  |   0.0923 |             0.0966 |        0.0966 |       0.0966 |
| 整体 RankICIR（年化）        |  12.8817 |            14.2859 |       14.2859 |      14.2859 |
| 整体 RankICIR（未年化）      |   0.8115 |             0.8999 |        0.8999 |       0.8999 |
| Net annualized               |    7.69% |              9.04% |        17.16% |       32.36% |
| 净累计收益                   |   30.63% |             36.64% |        77.06% |      174.92% |
| Net Sharpe                   |   0.3624 |             0.4054 |        0.7026 |       1.1571 |
| 净年化波动                   |   28.20% |             28.53% |        25.49% |       26.19% |
| 最大回撤                     |  -38.64% |            -40.67% |       -26.68% |      -24.91% |
| 日收益胜率                   |   53.47% |             53.47% |        51.93% |       55.89% |
| 日均双边换手                 |  198.83% |            199.35% |        19.23% |       40.02% |
| 日均费用 / 前日权益          |  0.1988% |            0.1993% |       0.0192% |      0.0400% |
| 已完成交易                   |   18,032 |             18,079 |         1,739 |        3,624 |
| 净超额年化 vs 市场均值       |   -3.47% |             -1.86% |         4.79% |       18.65% |
| Net IR vs 市场均值           |  -0.1404 |            -0.0649 |        0.4387 |       1.4547 |
| 净超额最大回撤 vs 市场均值   |  -28.47% |            -21.71% |       -19.46% |      -18.63% |
| 净超额年化 vs HS300 代理     |    2.77% |              4.09% |        11.53% |       26.04% |
| Net IR vs HS300 代理         |   0.2353 |             0.2947 |        0.6713 |       1.2699 |
| 净超额最大回撤 vs HS300 代理 |  -31.94% |            -29.34% |       -22.00% |      -23.96% |

### 同策略控制：Top20

| 指标                         | Alpha158 + 10d | Matched Alpha158 + 3d |
| ---------------------------- | -------------: | --------------------: |
| 整体 IC                      |         0.0530 |                0.0529 |
| 整体 RankIC                  |         0.0923 |                0.0922 |
| 整体 RankICIR（年化）        |        12.8817 |               12.9202 |
| 整体 RankICIR（未年化）      |         0.8115 |                0.8139 |
| Net annualized               |         18.69% |                22.62% |
| 净累计收益                   |         85.55% |               108.64% |
| Net Sharpe                   |         0.7414 |                0.9010 |
| 净年化波动                   |         26.13% |                24.72% |
| 最大回撤                     |        -32.24% |               -36.19% |
| 日收益胜率                   |         54.90% |                56.11% |
| 日均双边换手                 |         19.77% |                40.01% |
| 日均费用 / 前日权益          |        0.0198% |               0.0400% |
| 已完成交易                   |          1,799 |                 3,624 |
| 净超额年化 vs 市场均值       |          5.93% |                 9.01% |
| Net IR vs 市场均值           |         0.4543 |                0.6364 |
| 净超额最大回撤 vs 市场均值   |        -29.07% |               -25.97% |
| 净超额年化 vs HS300 代理     |         13.00% |                16.56% |
| Net IR vs HS300 代理         |         0.7197 |                0.9150 |
| 净超额最大回撤 vs HS300 代理 |        -26.76% |               -30.31% |

10 日策略下基础模型净年化 18.69%，高于增强模型 17.16%；3 日增强模型净年化 32.36%，高于匹配控制 22.62%，净 Sharpe 与回撤也改善。3 日相对 10 日增加换手，探索筛选不能作为独立确认，不据此改默认。

### 基准自身表现（908 日）

| Benchmark     | Annualized | Cumulative | Annualized volatility | Max drawdown | Daily win rate |
| ------------- | ---------: | ---------: | --------------------: | -----------: | -------------: |
| Universe mean |     11.12% |     46.22% |                25.06% |      -33.66% |         54.74% |
| HS300 proxy   |      5.03% |     19.33% |                17.58% |      -22.46% |         49.78% |

### Top30 辅助对比

| Scheme                | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| --------------------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158              |          0.99% |     0.1315 |      -40.59% |  199.03% |          -0.5933 |       -0.0776 |
| Factor: stock_risk    |          4.27% |     0.2480 |      -41.41% |  199.37% |          -0.4236 |        0.0840 |
| Strategy: 10d         |         18.60% |     0.7615 |      -28.32% |   19.45% |           0.5895 |        0.7631 |
| Strategy: 3d          |         29.29% |     1.0880 |      -25.53% |   40.03% |           1.4086 |        1.1912 |
| Alpha158 + 10d        |         22.57% |     0.8876 |      -31.95% |   19.78% |           0.7104 |        0.9347 |
| Matched Alpha158 + 3d |         20.43% |     0.8395 |      -33.71% |   40.02% |           0.5513 |        0.8412 |

### Top20 分年稳定性

| Year | Days | Alpha158 | Factor: stock_risk | Strategy: 10d | Strategy: 3d |
| ---- | ---: | -------: | -----------------: | ------------: | -----------: |
| 2023 |  242 |   -9.16% |            -10.08% |         5.39% |        9.65% |
| 2024 |  242 |    5.09% |             10.54% |         4.25% |       17.73% |
| 2025 |  243 |   48.64% |             56.68% |        43.69% |       72.54% |
| 2026 |  182 |   -9.30% |            -14.73% |        19.94% |       39.43% |

表中为各年区间的净年化，2026 年截至 10 月 8 日。所有方案均为 `incomplete_market_data`；缺行情可能延迟卖出并使用旧估值，结果是暂定评价。同收盘成交是代理假设。固定到期的 Top20 延迟退出累计事件为基础 84、因子 60；策略没有计划到期日，该字段为 0，不表示不存在受阻卖单。六组期末均有 20 个未结算持仓。

### 复现最终 Setting

先按[研究流程](workflow.md)准备行情并安装三个插件；每阶段保存 Task/Run ID 并等待成功后再提交下游，远程命令统一加同一 `--target`。以下训练显式列出会改变实验的参数；其余共同设置采用上表默认值，提交前用 `get_task_definition` 核对。各控制使用相同的基础行情、日历、标签文件。

```bash
# Base model: 158 features
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<base_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<base_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Final factor model: 158 base + 2 risk features
axonx submit --task qlib_factor_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_factor_train --source-tasks '<factor_etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --context-groups risk --context-windows '[10]' \
  --feature-fraction 1.0 --random-seed 42 --num-threads 8
axonx submit --task qlib_factor_predict --source-tasks '<factor_train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# Fixed holding: run once for base and once for factor predictions
axonx submit --task qlib_factor_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'

# Predeclared 10-day policy; change minimum-holding-days to 3 for exploration
axonx submit --task qlib_strategy_backtest --source-tasks '<factor_predict_task_id>' \
  --top-ns '[20,30]' --minimum-holding-days 10 \
  --replacement-fraction 0.2 --rank-buffer 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<base_etl_market_path>' --calendar-file '<base_etl_calendar_path>' \
  --labels-file '<base_etl_labels_path>'
```

基础固定到期控制将 task 改为 `qlib_a158_backtest` 并换入基础预测；基础 10 日控制仅换入基础预测。匹配 3 日控制使用同一增强 ETL 重新训练 `context_groups=none`、feature_fraction=1，其余设置不变，再预测并采用 3 日策略。新数据不能保证重现未发布的历史快照；不要复用同名任务覆盖已有结果。

### 最终任务来源与输入校验

执行工作区：45 机器 `/nas/jinli.yl/data/axon`；表中仅保留最终链路。

| Stage / scheme                  | Task ID                                          | Run ID                             |
| ------------------------------- | ------------------------------------------------ | ---------------------------------- |
| baseline: train                 | `train#qlib_a158_train#2026100912mMlp`           | `710de1c0530b430e94e0b92e7634cd2a` |
| baseline: predict               | `predict#qlib_a158_predict#2026100912Qanw`       | `c8b97e5ec7bb483da455d988ec6216d3` |
| full_none: train                | `train#qlib_factor_train#2026100916Lsy1`         | `a57d863cc3274580a3771faa31412f44` |
| full_none: predict              | `predict#qlib_factor_predict#2026100917IgPv`     | `3ad34a2542584fd8b6b6e70296ac4e6b` |
| stock_risk: train               | `train#qlib_factor_train#2026100917VGxi`         | `d55e035ab9c549ab840770b1e8444f10` |
| stock_risk: predict             | `predict#qlib_factor_predict#2026100917Z7Ys`     | `1a033666806b4e359c6acc11f8b02399` |
| Alpha158: backtest              | `backtest#qlib_a158_backtest#2026100916Y0Xb`     | `d10c8a78be104ee7a8a492b9cc438bde` |
| Factor: stock_risk: backtest    | `backtest#qlib_factor_backtest#2026100917v6ku`   | `37cf5867c5d344da9c4b6a9b56bc6e24` |
| Strategy: 10d: backtest         | `backtest#qlib_strategy_backtest#202610091847QW` | `f08ccc6d681648c9b63e96cacaad51b4` |
| Strategy: 3d: backtest          | `backtest#qlib_strategy_backtest#2026100918JP6A` | `6e7306c9d9a54cdeb6c2aee6a36bd73d` |
| Alpha158 + 10d: backtest        | `backtest#qlib_strategy_backtest#2026100918E4QT` | `3a28ad8734d949eb9b6289790dfe366b` |
| Matched Alpha158 + 3d: backtest | `backtest#qlib_strategy_backtest#20261009185kDS` | `f98fe8ba2d7045d1a7588e04a82301ca` |

| Input                             | SHA-256                                                            |
| --------------------------------- | ------------------------------------------------------------------ |
| market                            | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar                          | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels                            | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| Alpha158: prediction              | `3337bb98e59986b3d3e10730ecff49fae0d3d31b7d6b8e163fe19a63510a8aad` |
| Factor: stock_risk: prediction    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |
| Matched Alpha158 + 3d: prediction | `694553443c32336eb274e6998c884dd59444f0a5561381162c1fe236863b7101` |

基础 ETL：`etl#qlib_a158_etl#2026100912u43E`；最终增强 ETL：`etl#qlib_factor_etl#2026100917HM2p`。同模型各策略的预测哈希相同，六组行情、日历和标签哈希一致。框架/插件为 0.1.1 / 0.2.0，Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0；历史执行环境曾补入 portfolio_policy 扩展，部署时使用当前支持该扩展的源码版本。

[Alpha158](../../../plugins/qlib_a158/README_ZH.md#experiments) · [Qlib Factor](../../../plugins/qlib_factor/README_ZH.md#experiments) · [Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md#experiments)
