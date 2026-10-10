# Qlib Alpha158 插件

[English](README.md) · [简体中文](README_ZH.md) · [插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)

AxonX 基于 Qlib Alpha158 / LightGBM 研究方案开发的量化插件，提供数据处理、因子分析、模型训练、样本外预测和 TopN 回测。

使用 158 个价量特征作为研究基线。需要环境增强特征与消融实验时，参见 [Qlib Factor](../qlib_factor/README_ZH.md)。

## 与原始 Qlib 的差异

本插件采用 Alpha158 特征、日截面标签和 LightGBM 模型，使用 AxonX 组织数据处理、训练、预测与回测。Qlib `54355232463878d2eebb91fe0ee5fa7fa1f5976c` 的示例作为研究参考，具体方案与差异如下：

| 环节   | 本插件                                                                                | 原始 Qlib 示例                                               |
| ------ | ------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| 股票池 | 沪深全市场，排除北交所；训练筛选信号日可买样本                                        | 历史 CSI300 成分                                             |
| 特征   | 相同 158 个特征与窗口；极值索引跳过缺报价；近零波动相关性无效，回归保留交易日偏移     | Alpha158 表达式算子                                          |
| 数据   | Tushare 复权价格与成交量                                                              | Qlib 数据快照与采集器归一化                                  |
| 标签   | T→T+1 收盘收益，默认日截面 rank；两侧各剔除 2.5%                                      | T+1→T+2 收盘收益，DropnaLabel + CSZScoreNorm（样本标准差）   |
| 训练   | 末尾 10% 日期验证选轮数，再重拟合全部训练期；剔除跨截止日标签                         | 独立 train/valid/test，保留早停模型                          |
| 交易   | 当日收盘报价代理、官方涨跌停价格及分板块回退、默认每侧费用 0.2%，支持分别设置买卖费率 | 次日收盘、统一 9.5% 阈值、买入 0.05% / 卖出 0.15%，最低 5 元 |
| 策略   | 固定持有期 TopN；排名保留策略留在策略插件                                             | Top50、最多替换 5 只、95% 现金分配                           |
| 评价   | 复利净权益与 252 日年化；HS300 成分加权收益是代理基准                                 | CSI300 指数行情；风险分析默认算术累计                        |

每阶段 metadata 记录 `qlib_reference` / `qlib_deviations`，用于追踪参考版本和方案差异。

## 训练参数

训练默认 `parameter_preset=axonx`；`--parameter-preset qlib` 只切换超参数默认值，标签、股票池、种子、线程数、验证和重拟合流程保持一致；显式参数覆盖预设。

| 参数                            | axonx   | qlib                |
| ------------------------------- | ------- | ------------------- |
| learning_rate                   | 0.03    | 0.2                 |
| num_leaves / max_depth          | 31 / -1 | 210 / 8             |
| feature_fraction                | 0.9     | 0.8879              |
| bagging_fraction / bagging_freq | 0.9 / 1 | 0.8789 / 0          |
| lambda_l1 / lambda_l2           | 0 / 0   | 205.6999 / 580.9768 |

Qlib 的 `colsample_bytree` / `subsample` 分别对应 `feature_fraction` / `bagging_fraction`；其示例未配置 `subsample_freq`，因此 `qlib` 预设使用 `bagging_freq=0`。

## 参数实验

安装后可在成功 ETL 所在工作区本地执行 `rank/csz × axonx/qlib` 四组训练、预测和回测：

```bash
python -m axonx_qlib_a158.scripts.compare_parameters \
  --workspace-path /path/to/workspace --etl-task '<etl_task_id>' \
  --labels rank csz --train-start 20150101 --train-end 20230101 \
  --pred-start 20230101 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

脚本在本地复用同一 ETL，对每个标签分别运行两个模型参数预设，将验证指标、分期汇总、输入摘要和 Task ID 保存到工作区的 `qlib_a158_comparison/`。回测截止日取实际预测截止日；日期、TopN 和费用可通过 `--help` 配置。省略 `--labels` 时仅比较默认 rank 标签的两个参数预设。

## 安装与检查

要求 Python 3.12+ 和 AxonX `>=0.1.1,<0.2`；本地任务执行支持 macOS 和 Linux。安装在执行服务使用的 Python 环境中，再重启服务以重新加载插件。LightGBM、NumPy 和 Polars 随插件依赖安装。

```bash
pip install axonx-qlib-a158
axonx plugin list
axonx plugin show axonx-qlib-a158
```

源码开发时，在仓库根目录执行：

```bash
pip install -e ./plugins/qlib_a158
axonx plugin inspect ./plugins/qlib_a158
```

本机 CLI 的环境不一定是远程服务的环境。远程部署先配置目标服务 token，再明确指定目标：

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin install ./plugins/qlib_a158 --target 'http://<host>:1024'
axonx plugin list --target 'http://<host>:1024'
```

使用此源码仓库的 AxonX 核心时，通过远程安装 Job 更新仅贡献 Task 的 wheel，会刷新后续 Task 查询和提交，无需重启。仅在 `restart_required=true` 时重启，再查询 Task 定义核对字段。直接 `pip install`、editable 源码变更，以及不支持插件导入刷新的旧核心仍要求重启服务。分别设置买卖费率还要求执行环境的 AxonX 核心支持 `buy_cost_rate` / `sell_cost_rate`，可使用同一源码仓库中的核心版本。完整的构建、卸载和部署说明见[插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)。

## 数据准备

在执行服务环境配置 `AXONX_TUSHARE_TOKEN`，使用内置 `download_tushare_task` 准备工作区下的 Tushare Parquet 数据。默认 ETL 输入目录是工作区中的 `tushare/`，不是当前 shell 目录。

```bash
axonx submit --task download_tushare_task \
  --start-date 20140101 --end-date 20261008 \
  --datasets 'static,stk_limit,daily,adj_factor,index_weight'
```

保存返回的 `task_id` 和 `run_id`，等待下载成功后再提交 ETL：

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<download_task_id>' --run-id '<download_run_id>'
```

| 文件                                                             | 用途                                 |
| ---------------------------------------------------------------- | ------------------------------------ |
| `*/*/daily.parquet`, `*/*/adj_factor.parquet`                    | 行情与复权因子，必需                 |
| `trade_cal.parquet`, `stock_basic.parquet`, `namechange.parquet` | 交易日历、股票主数据和历史名称，必需 |
| `*/*/stk_limit.parquet`                                          | 官方涨跌停价格，影响可交易判断       |
| `*/*/index_weight.parquet`                                       | 沪深 300 成分权重，影响指数池与基准  |

`stock_basic.parquet` 必须包含 `ts_code`、`name`、`list_date` 和 `delist_date`；在市股票的退市日期可为空。内置 `download_tushare_task` 的 `static` 数据组会请求这些字段。最近 14 天刷新可使用 `--days-back 14`，默认同时下载主数据、涨跌停价格、日行情、复权因子和指数权重。

提前准备足够的历史数据供滚动窗口使用。示例训练期从 2015 年开始，因此下载从 2014 年开始。下载默认只回看七个自然日，不能据此假设历史数据齐全。数据凭据、分区布局与更新方式见 [Tushare 数据下载](https://flowllm-ai.github.io/AxonX/zh/research/tushare)。

ETL 从输出起始日前读取最长滚动窗口所需的市场日；更早且不参与本次计算的分区不会阻断任务。参与计算的行情和复权因子仍需通过完整校验。

## 任务与执行

| Task                 | 上游            | 产物                                 |
| -------------------- | --------------- | ------------------------------------ |
| `qlib_a158_etl`      | 工作区行情数据  | 特征、标签、交易状态和统计           |
| `qlib_a158_factor`   | ETL Task ID     | 因子诊断与分析结果                   |
| `qlib_a158_train`    | ETL Task ID     | 模型、训练协议、验证曲线和特征重要性 |
| `qlib_a158_predict`  | Train Task ID   | 全横截面预测与预测统计               |
| `qlib_a158_backtest` | Predict Task ID | 日级回测、分期汇总与持仓相关产物     |

因子分析从 ETL 分支执行，不是训练的前置任务。按以下顺序提交；每一步都使用实际返回的 Task ID，等待任务成功后再提交下游。

```bash
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008

# ETL 成功后
axonx submit --task qlib_a158_factor --source-tasks '<etl_task_id>'
axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101

# 训练成功后
axonx submit --task qlib_a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008

# 预测成功后
axonx submit --task qlib_a158_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

每次等待都同时提供本次运行的两个标识：

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<task_id>' --run-id '<run_id>'
axonx get_task_definition --task qlib_a158_train
```

远程执行时，上述提交、等待和定义查询命令都加上同一个 `--target`。不要只远程安装插件后又在本机环境执行任务。

## 关键参数

| 阶段 / 参数                                       | 默认值                  | 说明                               |
| ------------------------------------------------- | ----------------------- | ---------------------------------- |
| ETL `start_date` / `end_date`                     | `20140101` / null       | 输出起始日 / 最后日期，包含边界    |
| ETL `min_history_coverage`                        | `0.8`                   | 滚动特征最低历史覆盖率             |
| Train `train_start` / `train_end`                 | `20150101` / `20230101` | 训练起始日包含，截止日不包含       |
| Train `label_column`                              | `label_return_rank`     | 按日横截面排名的收益标签           |
| Train `label_winsorize_tail`                      | `0.025`                 | 训练 CSZ 标准化前各侧截尾比例      |
| Train `trim_tail`                                 | `0.025`                 | 按日剔除原始收益两端各 2.5%        |
| Train `validation_ratio`                          | `0.10`                  | 训练期末尾日期留作内部验证         |
| Train `num_boost_round` / `early_stopping_rounds` | `1000` / `50`           | 最大迭代 / 早停轮数                |
| Train `random_seed`                               | `42`                    | 模型抽样随机种子                   |
| Predict `pred_start` / `pred_end`                 | `20230101` / null       | 预测区间；起始日不能早于训练截止日 |
| Backtest `transaction_cost_rate`                  | `0.002`                 | 未设置分侧费率时使用的共用费率     |
| Backtest `buy_cost_rate`                          | `None`                  | 买入费率，未设沿用共用费率         |
| Backtest `sell_cost_rate`                         | `None`                  | 卖出费率，未设沿用共用费率         |
| Backtest `annualization_days`                     | `252`                   | 年化交易日数                       |

完整参数以执行环境中 `get_task_definition` 返回的 Schema 为准。

## 特征、标签与回测口径

158 个基础特征使用 `f_alpha158_*` 名称，包含 13 个当日价形特征以及 5、10、20、30、60 日窗口的 29 组滚动特征。行情使用复权价格，并保留交易日历和上市状态信息。

ETL 协议版本 2 发布独立的 `dataset`、`labels`、`market`、`calendar` 产物。原始标签固定为信号日到次一市场日的复权收益，停牌和缺数据使用无效标签，不寻找未来复牌收益。训练在排除截止时间之后的标签并处理尾部后，计算 `label_return_rank` 或 `label_return_csz`；拟合、验证和最终训练分别转换。rank 使用平均排名并归一化到 `[0,1]`；csz 使用截尾后的日截面总体标准差（`ddof=0`）。早停按验证 L2 选轮数。预测不依赖未来标签，统计描述分数和信号时选股资格。Studio 展示配置的 TopN，将行情不完整结果标为暂定评价。

回测继承 AxonX `BaseStockBacktestTask`，独立读取价格和交易状态，按每日市值估值。无法卖出时继续持仓并占用资金，所选股票无法买入时不以低分股票补位。`transaction_cost_rate` 为共用费率；`buy_cost_rate` / `sell_cost_rate` 可分别覆盖买入与卖出费率，未设的单侧沿用共用费率。使用 `--buy-cost-rate 0.0005 --sell-cost-rate 0.0015` 可按 qlib 的买入 0.05% / 卖出 0.15% 收费，归一化资金账本不设最低 5 元费用。费用按实际成交金额收取，`top_ns` 是整数列表。`market_status_file` 可提供经确认的停牌状态（信号主键及 `market_status=suspended`）；缺行情不自动视为停牌，相关回测标为 `incomplete_market_data`。Top30 是信号目标，实际持仓、订单及已完成交易分别见 `positions`、`orders`、`trades`。

收益、成本、IC 与持仓的详细定义见 [回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)。

预测文件对接回测的必需列、可选列及 metadata 约束见[预测输入契约](../../docs/zh/reference/research-artifacts.md#预测到股票回测的输入契约)。

## 本地验证

在仓库根目录安装开发依赖后执行：

```bash
.venv/bin/python -m pytest \
  tests/unit/test_qlib_a158.py tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py \
  tests/unit/test_stock_backtest.py tests/unit/test_stock_pipeline.py -q
```

覆盖特征边界、标签时点、四组参数对照、分侧费用、延迟退出与持仓资金记账规则。

<a id="experiments"></a>

## 最终实验设定与结果

本节记录本插件的最终实验；跨插件对比见[三层实验对比](../../docs/zh/research/experiments.md#comparison)。指标整理自 45 机器成功任务的 metadata、summary.parquet、daily.parquet 和 trades.parquet，原始产物保留在执行工作区。

### 详细 Setting

| 环节            | 设定                                                                                                                                                                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数据 / 股票池   | Tushare 复权价量；沪深全市场，排除北交所，不限制 CSI300 成分选股。ETL 输出 20150101–20261008，共 11,446,950 行、5,477 只股票；158 个模型特征。min_history_coverage=0.8；停牌、缺报价不前向填充。                                              |
| 训练日期        | `[20150101,20230101)`；信号日与 label_target_date 都早于排他的训练截止日。内部验证从 20220316 开始，按末尾 10% 日期划分。                                                                                                                     |
| 标签 / 样本     | T→次一市场日复权收盘收益；只保留信号日可买、固定一日标签有效且在截止日前可取得的样本。每日原始收益两侧各剔除 2.5%，rank 用平均名次归一化至 [0,1]，单样本为 0.5；拟合与验证分开转换。label_winsorize_tail=0.025；本实验使用 rank，不使用 CSZ。 |
| 样本数量        | 截尾前 6,147,420 行；截尾后全期重拟合 5,838,557 行；调参训练 5,010,901 行、内部验证 823,601 行。                                                                                                                                              |
| LightGBM        | 4.7.0，parameter_preset=axonx，objective=regression，metric=[l2,l1]；learning_rate=0.03，num_leaves=31，max_depth=-1，min_data_in_leaf=20，bagging_fraction=0.9，bagging_freq=1，lambda_l1=lambda_l2=0。feature_fraction=0.9。                |
| 选轮数 / 重拟合 | num_boost_round=1000，early_stopping_rounds=50；以内部验证 L2 选轮数后重拟合全部训练样本。                                                                                                                                                    |
| 确定性          | random_seed=42；LightGBM seed、feature_fraction_seed、bagging_seed、data_random_seed 均为 42；num_threads=8，deterministic=true，force_col_wise=true。                                                                                        |
| 样本外          | pred_start=20230101，pred_end=20261008；实际整体评估 20230103–20261008，909 个市场日，2026 为不完整年度。                                                                                                                                     |
| 组合 / 成交     | 重点 Top20，Top30 辅助；收盘报价为成交代理，先卖后买，遵循涨跌停与可交易限制；新仓最多分配 1/N 权益，不能买入不补位，不能卖出继续持仓并占用资金，保留仓位不再平衡；不强制期末清仓。                                                           |
| 费用 / 年化     | transaction_cost_rate=0.001，每次实际成交买卖各 0.1%；buy_cost_rate=sell_cost_rate=null，沿用共用费率，不设最低费用。annualization_days=252，annual_risk_free_rate=0.012。                                                                    |
| 输入对齐        | 本次回测使用上游 ETL 的 market.parquet、calendar.parquet、labels.parquet；as_of_date=20261008，index_codes=[]，minimum_index_weight_coverage=0.98。                                                                                           |

本次模型使用 158 个特征，早停选择 422 轮后全训练期重拟合，内部验证 RankIC 为 0.10789。

本次使用固定持有期 `holding_days=1`。

### 指标口径

整体 IC/RankIC 是信号日可选股票中有效次日标签与预测的每日 Pearson/Spearman 相关系数均值，与持仓 TopN 和策略无关。RankICIR 未年化值为 mean(日 RankIC)/std(日 RankIC,ddof=1)，年化值再乘 sqrt(252)；表中两种均列出，避免与不年化的因子分析口径混淆。

净年化 = (∏(1+r_net))^(252/D)−1；净 Sharpe = (mean(r_net)−[(1.012)^(1/252)−1])/std(r_net,ddof=1)×sqrt(252)。最大回撤基于复利净权益，峰值包含初始权益 1；换手 = (实际买入金额+卖出金额)/前日权益，全部换仓约 200%。胜率为净日收益大于 0 的比例。

“市场均值”基准是有有效前向标签的预测全截面股票等权平均收益，不是仅 Top20，也不是风险因子计算中的缩尾均值。HS300 为信号中沪深 300 成分权重加权收益的代理，权重覆盖至少 98%；不是官方 CSI300 指数行情。两个基准的有效日期均为 20230104–20261008（908 日），净超额指标只用该共同窗口；组合自身指标用完整 909 日。

扣费日超额 a_t = r_net,t−r_benchmark,t；**Net IR（净信息比率）** = mean(a)/std(a,ddof=1)×sqrt(252)。净超额年化用 ∏(1+a) 复利并按 908 日年化；净超额最大回撤也基于这条超额复利曲线。它们不是两个年化收益相减，也不是组合/基准权益比；原框架 information_ratio 字段用毛收益，本节重新从日级产物计算扣费指标。

### 整体信号与 Top20 完整结果

| 指标                         | Alpha158 |
| ---------------------------- | -------: |
| 整体 IC                      |   0.0530 |
| 整体 RankIC                  |   0.0923 |
| 整体 RankICIR（年化）        |  12.8817 |
| 整体 RankICIR（未年化）      |   0.8115 |
| Net annualized               |    7.69% |
| 净累计收益                   |   30.63% |
| Net Sharpe                   |   0.3624 |
| 净年化波动                   |   28.20% |
| 最大回撤                     |  -38.64% |
| 日收益胜率                   |   53.47% |
| 日均双边换手                 |  198.83% |
| 日均费用 / 前日权益          |  0.1988% |
| 已完成交易                   |   18,032 |
| 净超额年化 vs 市场均值       |   -3.47% |
| Net IR vs 市场均值           |  -0.1404 |
| 净超额最大回撤 vs 市场均值   |  -28.47% |
| 净超额年化 vs HS300 代理     |    2.77% |
| Net IR vs HS300 代理         |   0.2353 |
| 净超额最大回撤 vs HS300 代理 |  -31.94% |

### Top30 结果

| Scheme   | Net annualized | Net Sharpe | Max drawdown | Turnover | Net IR: universe | Net IR: HS300 |
| -------- | -------------: | ---------: | -----------: | -------: | ---------------: | ------------: |
| Alpha158 |          0.99% |     0.1315 |      -40.59% |  199.03% |          -0.5933 |       -0.0776 |

### Top20 分年结果

| Year | Days | Alpha158 |
| ---- | ---: | -------: |
| 2023 |  242 |   -9.16% |
| 2024 |  242 |    5.09% |
| 2025 |  243 |   48.64% |
| 2026 |  182 |   -9.30% |

各年值为对应区间净年化；2026 年截至 10 月 8 日。结果为 `incomplete_market_data`，缺报价可能延迟退出并沿用旧估值，同收盘成交为代理假设。

### 复现实验

每阶段保存返回的 Task/Run ID 并等待成功后再提交下游；远程执行时统一使用同一 `--target`。以下参数与 Setting 表一致，其余默认值提交前用 `get_task_definition` 核对。

```bash
axonx submit --task qlib_a158_etl --start-date 20150101 --end-date 20261008
axonx submit --task qlib_a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101 --label-column label_return_rank \
  --parameter-preset axonx --feature-fraction 0.9 \
  --random-seed 42 --num-threads 8
axonx submit --task qlib_a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008
axonx submit --task qlib_a158_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --holding-days 1 --transaction-cost-rate 0.001 \
  --as-of-date 20261008 --annualization-days 252 --annual-risk-free-rate 0.012 \
  --market-file '<market_path>' --calendar-file '<calendar_path>' --labels-file '<labels_path>'
```

### 任务来源与输入校验

执行工作区：45 机器 `/nas/jinli.yl/data/axon`。

| Stage / scheme     | Task ID                                      | Run ID                             |
| ------------------ | -------------------------------------------- | ---------------------------------- |
| baseline: train    | `train#qlib_a158_train#2026100912mMlp`       | `710de1c0530b430e94e0b92e7634cd2a` |
| baseline: predict  | `predict#qlib_a158_predict#2026100912Qanw`   | `c8b97e5ec7bb483da455d988ec6216d3` |
| Alpha158: backtest | `backtest#qlib_a158_backtest#2026100916Y0Xb` | `d10c8a78be104ee7a8a492b9cc438bde` |

| Input    | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `3337bb98e59986b3d3e10730ecff49fae0d3d31b7d6b8e163fe19a63510a8aad` |

框架/插件版本为 0.1.1 / 0.2.0；Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0。新数据不保证重现未发布的历史快照；原始运行产物不随仓库提交。
