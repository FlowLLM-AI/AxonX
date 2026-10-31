# Qlib Alpha158 插件

[English](README.md) · [简体中文](README_ZH.md) · [插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)

AxonX 基于 Qlib Alpha158 / LightGBM 研究方案开发的离线量化研究插件，提供数据处理、因子分析、模型训练、样本外预测、组合构建和 TopN 回测。Task 以已准备好的历史 Parquet 数据为输入。

使用 158 个价量特征作为研究基线。需要环境增强特征与消融实验时，参见 [Qlib Factor](../qlib_factor/README_ZH.md)。

## 与原始 Qlib 的差异

本插件采用 Alpha158 特征、日截面标签和 LightGBM 模型，使用 AxonX 组织数据处理、训练、预测与回测。Qlib `54355232463878d2eebb91fe0ee5fa7fa1f5976c` 的示例作为研究参考，具体方案与差异如下：

| 环节   | 本插件                                                                            | 原始 Qlib 示例                                               |
| ------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| 股票池 | 沪深全市场，排除北交所；训练筛选信号日可买样本                                    | 历史 CSI300 成分                                             |
| 特征   | 相同 158 个特征与窗口；极值索引跳过缺报价；近零波动相关性无效，回归保留交易日偏移 | Alpha158 表达式算子                                          |
| 数据   | Tushare 复权价格与成交量                                                          | Qlib 数据快照与采集器归一化                                  |
| 标签   | T→T+1 收盘收益，默认日截面 rank；两侧各剔除 2.5%                                  | T+1→T+2 收盘收益，DropnaLabel + CSZScoreNorm（样本标准差）   |
| 训练   | 末尾 10% 日期验证选轮数，再重拟合全部训练期；剔除跨截止日标签                     | 独立 train/valid/test，保留早停模型                          |
| 交易   | 当日收盘报价代理、官方涨跌停价格及分板块回退、默认买入 0.05% / 卖出 0.15%         | 次日收盘、统一 9.5% 阈值、买入 0.05% / 卖出 0.15%，最低 5 元 |
| 策略   | Portfolio 定义 TopN 策略；各组合的 `portfolio_id` 记录策略与参数                  | Top50、最多替换 5 只、95% 现金分配                           |
| 评价   | 复利净权益与 252 日年化；HS300 成分加权收益是代理基准                             | CSI300 指数行情；风险分析默认算术累计                        |

每阶段 metadata 记录 `qlib_reference` / `qlib_deviations`，用于追踪参考版本和方案差异。

## 训练参数

训练默认 `parameter_preset=axonx`；`--parameter-preset qlib` 只切换超参数默认值，标签、股票池、种子、线程数、验证和重拟合流程保持一致；显式参数覆盖预设；数值训练参数必须为有限值。

| 参数                            | axonx   | qlib                |
| ------------------------------- | ------- | ------------------- |
| learning_rate                   | 0.03    | 0.2                 |
| num_leaves / max_depth          | 31 / -1 | 210 / 8             |
| feature_fraction                | 0.9     | 0.8879              |
| bagging_fraction / bagging_freq | 0.9 / 1 | 0.8789 / 0          |
| lambda_l1 / lambda_l2           | 0 / 0   | 205.6999 / 580.9768 |

Qlib 的 `colsample_bytree` / `subsample` 分别对应 `feature_fraction` / `bagging_fraction`；其示例未配置 `subsample_freq`，因此 `qlib` 预设使用 `bagging_freq=0`。

## 安装与检查

插件版本 0.3.0 要求 Python 3.12+ 和 AxonX `>=0.3.0`；任务执行支持 macOS 和 Linux。安装在运行 `axonx exec` 的 Python 环境中，使用 `--target` 时为目标服务解释器。LightGBM、NumPy 和 Polars 随插件依赖安装。

插件尚未发布到 PyPI。先克隆仓库并从根目录安装匹配的主包，再将插件安装为 wheel：

```bash
git clone https://github.com/FlowLLM-AI/AxonX.git
cd AxonX
pip install -e .
axonx plugin install ./plugins/qlib_a158
axonx plugin list
axonx plugin show axonx-qlib-a158
```

源码开发时，在仓库根目录执行：

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin inspect ./plugins/qlib_a158
```

editable 需要选定 Python 环境中的源码目录，不能与 `--output` 同用；指定 `--target` 时源码目录属于目标机器。新的 `exec` 进程加载当前 Python 源码；依赖或入口点变化后重新安装，重启常驻服务以刷新 Task 目录、Schema 和已加载依赖。

本机 CLI 的环境不一定是远程服务的环境。远程部署先配置目标服务 token，再明确指定目标：

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
# 先上传 /tmp/axonx-wheels 中实际构建的 wheel，再执行安装。
axonx plugin install '<uploaded answer.location>' --target 'http://<host>:1024' --client-timeout 600
axonx plugin list --target 'http://<host>:1024'
```

安装修改所选解释器；新 CLI 进程发现已安装插件，定义查询和 Studio 则保留服务启动时的目录，直到重启。安装或核验失败时停止并报告。[插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)

上传安装后，使用工作区相对 `path` 清理暂存文件；安装源使用绝对 `location`。通过 `axonx restart_service --target HOST:PORT` 重启，待服务恢复后核验插件版本和 Task 定义。链接中的部署指南包含上传、校验和清理的完整示例。

## 执行与配置

`axonx exec` 在本地 CLI 进程中同步执行并打印输出参数，以退出码判断命令成功，可在无服务时运行。指定 `--target` 后，命令在目标服务的 CLI 子进程中执行。定义、状态和日志 Job 需要运行中的服务，查询该服务的环境与工作区。

执行配置优先级为：显式 CLI 参数 → 服务 `get_config` → 内置默认值。使用 `--workspace-dir /absolute/path` 明确选择研究工作区；ETL 相对输入路径从工作区解析。本地和远程命令必须使用上游 Task 所在的工作区。

使用标准应用配置，已安装插件的 `plugin.yaml` 贡献 Task 注册；研究输入通过 `exec` 参数传入：

```bash
axonx app --workspace-dir /tmp/axonx-research
# 在另一终端执行；该工作区需已准备历史数据：
axonx exec --task qlib_a158_research --task-name baseline --workspace-dir /tmp/axonx-research
axonx status --task-id 'base#qlib_a158_research#baseline' --detail full
```

Task ID 格式为 `<type>#<registration>#<task_name>`。从日志或完整状态保存 ID 和 `started_at`；同名重跑替换该 Task 的当前产物。父子调用表示流程组合，`upstream_task_ids` 表示消费数据的依赖；展示副本不能作为研究输入。

## 数据准备

在执行服务环境配置 `AXONX_TUSHARE_TOKEN`，使用内置 `download_tushare_task` 准备工作区下的 Tushare Parquet 数据。默认 ETL 输入目录是工作区中的 `tushare/`，不是当前 shell 目录。

```bash
axonx exec --task download_tushare_task \
  --start-date 20140101 --end-date 20261008 \
  --datasets 'static,stk_limit,daily,adj_factor,index_weight'
```

`axonx exec` 返回最终退出码；下载成功后再执行 ETL。

| 文件                                                             | 用途                                 |
| ---------------------------------------------------------------- | ------------------------------------ |
| `*/*/daily.parquet`, `*/*/adj_factor.parquet`                    | 行情与复权因子，必需                 |
| `trade_cal.parquet`, `stock_basic.parquet`, `namechange.parquet` | 交易日历、股票主数据和历史名称，必需 |
| `*/*/stk_limit.parquet`                                          | 官方涨跌停价格，影响可交易判断       |
| `*/*/index_weight.parquet`                                       | 沪深 300 成分权重，影响指数池与基准  |

`stock_basic.parquet` 必须包含 `ts_code`、`name`、`list_date` 和 `delist_date`；在市股票的退市日期可为空。内置 `download_tushare_task` 的 `static` 数据组会请求这些字段。最近 14 天刷新可使用 `--days-back 14`，默认同时下载主数据、涨跌停价格、日行情、复权因子和指数权重。

提前准备足够的历史数据供滚动窗口使用。示例训练期从 2015 年开始，因此下载从 2014 年开始。下载默认只回看七个自然日，不能据此假设历史数据齐全。数据凭据、分区布局与更新方式见 [Tushare 数据下载](https://flowllm-ai.github.io/AxonX/zh/research/tushare)。

ETL 从输出起始日前读取最长滚动窗口所需的市场日；更早且不参与本次计算的分区不会阻断任务。参与计算的行情和复权因子仍需通过完整校验。

## 一次执行研究流程

`qlib_a158_research` 使用普通子 Task 执行 ETL → Train → Predict → Portfolio → Backtest；提供 `analysis` 时还会从 ETL 分支运行因子分析。每个子任务有独立状态、日志和产物，父任务记录 `stage_task_ids`。

```bash
axonx exec --task qlib_a158_research --task-name baseline \
  --etl '{"start_date":"20150101","end_date":"20261008"}' \
  --train '{"train_start":"20150101","train_end":"20230101","parameter_preset":"axonx"}' \
  --predict '{"pred_end":"20261008"}' \
  --portfolio '{"top_ns":[5,10,20,30]}' \
  --analysis '{}'
```

未指定预测起点时使用训练截止日；不传 `analysis` 则跳过因子诊断。研究参数属于插件，不放入服务 YAML。历史数据需提前准备；流程不会自动下载历史行情。子任务名称和依赖由父任务管理。

回测默认截至最后信号日。需要继续估值或结算末期持仓时，在 `backtest.as_of_date` 中明确指定截止日。

叶子预测任务可同时指定一个 Train 和一个 ETL 上游，用已有模型预测新数据；插件检查特征语义一致性。只指定 Train 时使用它的训练 ETL。

## 任务与执行

| Task                  | 上游               | 产物                                 |
| --------------------- | ------------------ | ------------------------------------ |
| `qlib_a158_etl`       | 工作区行情数据     | 特征、标签、交易状态和统计           |
| `qlib_a158_analysis`  | ETL 任务标识       | 因子诊断与分析结果                   |
| `qlib_a158_train`     | ETL 任务标识       | 模型、训练协议、验证曲线和特征重要性 |
| `qlib_a158_predict`   | Train + 可选 ETL   | 全横截面预测与预测统计               |
| `qlib_a158_portfolio` | Predict 任务标识   | 冻结的组合计划、信号排名与策略身份   |
| `qlib_a158_backtest`  | Portfolio 任务标识 | 日级回测、分期汇总与持仓相关产物     |

因子分析从 ETL 分支执行，不是训练的前置任务。按以下顺序提交；从执行日志记录 Task ID，等待任务成功后再提交下游。

```bash
axonx exec --task qlib_a158_etl --start-date 20150101 --end-date 20261008

# ETL 成功后
axonx exec --task qlib_a158_analysis --upstream-task-ids '["<etl_task_id>"]'
axonx exec --task qlib_a158_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101

# 训练成功后
axonx exec --task qlib_a158_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008

# 预测成功后
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<predict_task_id>"]' --top-ns '[5,10,20,30]'
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<portfolio_task_id>"]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

使用 `axonx get_task_def --task qlib_a158_train` 检查输入输出 schema。远程执行和定义查询都加上同一个 `--target`，使用目标服务的 Python 环境。

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
| Backtest `buy_cost_rate`                          | `0.0005`                | 买入成交金额费用率                 |
| Backtest `sell_cost_rate`                         | `0.0015`                | 卖出成交金额费用率                 |
| Backtest `annualization_days`                     | `252`                   | 年化交易日数                       |

完整参数以执行环境中 `get_task_def` 返回的 Schema 为准。

## 特征、标签与回测口径

158 个基础特征使用 `f_alpha158_*` 名称，包含 13 个当日价形特征以及 5、10、20、30、60 日窗口的 29 组滚动特征。行情使用复权价格，并保留交易日历和上市状态信息。

ETL 使用协议 v1 发布独立的 `dataset`、`labels`、`market`、`calendar` 产物。原始标签固定为信号日到次一市场日的复权收益，停牌和缺数据使用无效标签，不寻找未来复牌收益。训练在排除截止时间之后的标签并处理尾部后，计算 `label_return_rank` 或 `label_return_csz`；拟合、验证和最终训练分别转换。rank 使用平均排名并归一化到 `[0,1]`；csz 使用截尾后的日截面总体标准差（`ddof=0`）。早停按验证 L2 选轮数。预测不依赖未来标签，统计描述分数和信号时选股资格。Studio 展示配置的 TopN，将行情不完整结果标为暂定评价。

回测继承 AxonX `BaseStockBacktestTask`，独立读取价格和交易状态，按每日市值估值。无法卖出时继续持仓并占用资金，所选股票无法买入时不以低分股票补位。`buy_cost_rate=0.0005` 和 `sell_cost_rate=0.0015` 默认使用 Qlib 参考费率，即买入 0.05% / 卖出 0.15%，归一化资金账本不设最低 5 元费用。费用按实际成交金额收取，`top_ns` 是整数列表。`market_status_file` 可提供经确认的停牌状态（信号主键及 `market_status=suspended`）；缺行情不自动视为停牌，相关回测标为 `incomplete_market_data`。Top30 是信号目标，实际持仓、订单及已完成交易分别见 `positions`、`orders`、`trades`。

收益、成本、IC 与持仓的详细定义见 [回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)。

预测文件对接回测的必需列、可选列及 metadata 约束见[预测输入契约](../../docs/zh/reference/research-artifacts.md#预测到股票回测的输入契约)。

## 本地验证

在仓库根目录安装开发依赖后执行：

```bash
python -m pytest \
  plugins/qlib_a158/tests \
  tests/unit/test_stock_backtest.py tests/unit/test_documentation_contracts.py -q
```

覆盖 CPU 组合研究流程、新数据预测、特征协议校验、标签/预设对照和共享股票账本。跨插件测试需要安装全部三个研究插件。

使用已成功完成的 ETL 运行比较 analysis Task。汇总表和比较清单保存在该 Task 目录，metadata 记录子任务身份：

```bash
axonx exec --task qlib_a158_compare --task-name preset-comparison \
  --workspace-dir /tmp/axonx-research --upstream-task-ids '["<etl_task_id>"]' --labels '["rank","csz"]'
```

比较任务使用普通 CLI 执行配置和子任务生命周期，`summary_stats.csv` 与 `comparison.json` 记录各阶段 Task ID、`started_at` 和输入版本。嵌套的 `train`、`predict`、`backtest` 选项复用对应阶段参数及默认值；`predict.pred_start` 必须不早于 `train.train_end`。子任务名字、依赖、训练预设与标签、回测输入与截止日由比较任务控制，不接受对应嵌套选项。

## 实验记录

共享设定、结果、复现命令和 Task 来源统一维护在 [Alpha158 改进实验](../../docs/zh/research/alpha158-case.md)。产物字段与股票池报告遵循[共享协议](../../docs/zh/reference/research-artifacts.md)。
