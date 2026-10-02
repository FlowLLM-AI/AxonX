# Alpha158 插件

[English](README.md) · [简体中文](README_ZH.md) · [插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)

独立的 AxonX 量化研究插件，提供数据处理、因子分析、LightGBM 训练、样本外预测和 TopN 回测。

使用 158 个价量特征作为研究基线。需要环境增强特征与消融实验时，参见 [Alpha158 Enhanced](../a158_enhanced/README_ZH.md)。

![研究任务与产物链路](../../docs/figures/research/workflow.svg)

## 安装与检查

要求 Python 3.12+；本地任务执行支持 macOS 和 Linux。安装在执行服务使用的 Python 环境中，再重启服务以重新加载插件。LightGBM、NumPy 和 Polars 随插件依赖安装。

```bash
pip install axonx-alpha158
axonx plugin list
axonx plugin show axonx-alpha158
```

源码开发时，在仓库根目录执行：

```bash
pip install -e ./plugins/a158
axonx plugin inspect ./plugins/a158
```

本机 CLI 的环境不一定是远程服务的环境。远程部署先配置目标服务 token，再明确指定目标：

```bash
export AXONX_TARGET_TOKEN='<service token>'
axonx plugin install ./plugins/a158 --target 'http://<host>:1024'
axonx plugin list --target 'http://<host>:1024'
```

按安装响应中的 `restart_required` 重启目标服务，再查询 Task 定义。完整的构建、卸载和部署说明见[插件管理](https://flowllm-ai.github.io/AxonX/zh/plugins/management)。

## 数据准备

在执行服务环境配置 `AXONX_TUSHARE_TOKEN`，使用内置 `download_tushare_task` 准备工作区下的 Tushare Parquet 数据。默认 ETL 输入目录是工作区中的 `tushare/`，不是当前 shell 目录。

```bash
axonx submit --task download_tushare_task \
  --start-date 20140101 --end-date 20260930 \
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

提前准备足够的历史数据供滚动窗口使用。示例训练期从 2015 年开始，因此下载从 2014 年开始。下载默认只回看七个自然日，不能据此假设历史数据齐全。数据凭据、分区布局与更新方式见 [Tushare 数据下载](https://flowllm-ai.github.io/AxonX/zh/research/tushare)。

## 任务与执行

| Task            | 上游            | 产物                                 |
| --------------- | --------------- | ------------------------------------ |
| `a158_etl`      | 工作区行情数据  | 特征、标签、交易状态和统计           |
| `a158_factor`   | ETL Task ID     | 因子诊断与分析结果                   |
| `a158_train`    | ETL Task ID     | 模型、训练协议、验证曲线和特征重要性 |
| `a158_predict`  | Train Task ID   | 全横截面预测与预测统计               |
| `a158_backtest` | Predict Task ID | 日级回测、分期汇总与持仓相关产物     |

因子分析从 ETL 分支执行，不是训练的前置任务。按以下顺序提交；每一步都使用实际返回的 Task ID，等待任务成功后再提交下游。

```bash
axonx submit --task a158_etl --start-date 20150101 --end-date 20260930

# ETL 成功后
axonx submit --task a158_factor --source-tasks '<etl_task_id>'
axonx submit --task a158_train --source-tasks '<etl_task_id>' \
  --train-start 20150101 --train-end 20230101

# 训练成功后
axonx submit --task a158_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20260930

# 预测成功后
axonx submit --task a158_backtest --source-tasks '<predict_task_id>'
```

每次等待都同时提供本次运行的两个标识：

```bash
axonx --client-timeout 86400 wait_task \
  --task-id '<task_id>' --run-id '<run_id>'
axonx get_task_definition --task a158_train
```

远程执行时，上述提交、等待和定义查询命令都加上同一个 `--target`。不要只远程安装插件后又在本机环境执行任务。

![Studio 任务血缘](../../docs/figures/studio/task-lineage.png)

## 关键参数

| 阶段 / 参数                                       | 默认值                  | 说明                               |
| ------------------------------------------------- | ----------------------- | ---------------------------------- |
| ETL `start_date` / `end_date`                     | `20140101` / null       | 输出起始日 / 最后日期，包含边界    |
| ETL `min_history_coverage`                        | `0.8`                   | 滚动特征最低历史覆盖率             |
| Train `train_start` / `train_end`                 | `20150101` / `20230101` | 训练起始日包含，截止日不包含       |
| Train `label_column`                              | `label_1d_rank`         | 按日横截面排名的收益标签           |
| Train `trim_tail`                                 | `0.025`                 | 按日剔除原始收益两端各 2.5%        |
| Train `validation_ratio`                          | `0.10`                  | 训练期末尾日期留作内部验证         |
| Train `num_boost_round` / `early_stopping_rounds` | `1000` / `50`           | 最大迭代 / 早停轮数                |
| Train `random_seed`                               | `42`                    | 模型抽样随机种子                   |
| Predict `pred_start` / `pred_end`                 | `20230101` / null       | 预测区间；起始日不能早于训练截止日 |
| Backtest `transaction_cost_rate`                  | `0.002`                 | 乘以每日实际换手率的交易成本       |
| Backtest `annualization_days`                     | `252`                   | 年化交易日数                       |

完整参数以执行环境中 `get_task_definition` 返回的 Schema 为准。

## 特征、标签与回测口径

原始特征使用 `f_alpha158_*` 名称，包含 13 个当日价形特征以及 5、10、20、30、60 日窗口的 29 组滚动特征。行情使用复权价格，并保留交易日历和上市状态信息。

正常标签为信号日 T 收盘至 T+1 收盘的复权收益；无法按计划卖出时延迟至首个可卖日期。训练、因子和信号排名评估仅使用有效且未延迟的一日样本。预测保留完整横截面，不事先按未来标签筛掉股票。

回测按当天信号排名并用当天收盘价模拟买入，使用日线可交易代理；未模拟盘后排队与部分成交。持仓锁定资金直到实际退出，未结清持仓按成本记账，净收益在退出日确认。Top30 持仓明细是信号目标，不等于实际持仓账本。

收益、成本、IC 与持仓的详细定义见 [回测解读](https://flowllm-ai.github.io/AxonX/zh/research/backtest)。

## 在 Studio 查看结果

在任务详情检查参数、日志、metadata 和上游关系；在研究结果页面查看 ETL、因子、训练、预测和回测产物。下图是已有实验的界面示例，不代表本插件每次运行的结果。

![训练曲线](../../docs/figures/studio/training-curves.png)

![样本外预测](../../docs/figures/studio/prediction-results.png)

![回测整体指标](../../docs/figures/studio/backtest-overall.png)

## 排查问题与源码

| 问题            | 检查项                                                      |
| --------------- | ----------------------------------------------------------- |
| 没有注册的 Task | 安装环境、插件入口、服务重启和目标机器                      |
| ETL 缺少数据    | 工作区 tushare 分区和三个静态文件；历史日期覆盖             |
| 预测日期报错    | pred_start 必须不早于 train_end，且模型与 ETL metadata 完整 |
| 结果与示例不同  | 数据快照、特征组、区间、标签、参数和成本是否一致            |

[插件注册](axonx_alpha158/plugin.yaml) · [ETL](axonx_alpha158/etl.py) · [因子分析](axonx_alpha158/analysis.py) · [训练](axonx_alpha158/train.py) · [预测](axonx_alpha158/predict.py) · [回测](axonx_alpha158/backtest.py)

[研究流程](https://flowllm-ai.github.io/AxonX/zh/research/workflow) · [研究结果](https://flowllm-ai.github.io/AxonX/zh/research/results) · [任务管理](https://flowllm-ai.github.io/AxonX/zh/guides/task-management)

仓库中的 [run_pipeline.sh](axonx_alpha158/scripts/run_pipeline.sh) 提供自动提取句柄、逐阶段等待与失败退出的串联示例；它只刷新最近七天的行情，使用前仍须准备完整历史数据。

## 本地验证

在仓库根目录安装开发依赖后执行：

```bash
.venv/bin/python -m pytest \
  tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py -q
```

覆盖标签时点、延迟退出、费用与持仓资金记账规则。
