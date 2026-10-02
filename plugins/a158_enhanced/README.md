# Alpha158 环境增强插件

独立复制自 `plugins/a158`。沿用原始158个特征和收盘标签，增加26个市场环境、成交金额分组、相对表现及交互特征。成交金额表示交易活跃度，不表示市值。

本文件是插件说明、实验文档和复现材料的统一入口。源代码在 `axonx_alpha158_enhanced`，不依赖原插件的Python包。

## 1. 实验文档索引

建议按以下顺序阅读：

| 顺序 | 文档 | 内容 |
| ---: | --- | --- |
| 1 | [实验计划](DEVELOPMENT_PLAN.md) | 研究目标、数据与信号时点、候选特征、训练/筛选/确认区间、控制变量和筛选规则 |
| 2 | [实验过程](EXPERIMENT_PROCESS.md) | 实施步骤、验证检查、异常修复、任务时间及Task/Run ID、方案锁定、最终安装 |
| 3 | [实验结果](EXPERIMENT_RESULTS.md) | 消融比较、全部TopN、分年和市场环境表现、配对统计区间、特征重要性及局限 |

复现与核查材料见下方[实验材料索引](#3-实验材料索引)、[实现索引](#4-实现索引)、[远程运行与复现](#6-远程运行与复现)和[本地验证](#7-本地验证)。

## 2. 当前版本与结论

0.1.2默认启用四组完整方案，与筛选期锁定并经过确认期评估的184特征方案一致。该组合提升了确认期RankIC和Top10/20净年化收益，但Top1–3收益及RankICIR下降，确认期增量的bootstrap区间跨零，不能称为所有指标均改善。

## 3. 实验材料索引

[experiments/README.md](experiments/README.md) 列出随仓库提交的指标与校验汇总：

| 阶段 | 材料 | 用途 |
| --- | --- | --- |
| 数据检查 | [原始字段逐值对照](experiments/baseline_data_parity.json)、[特征覆盖率](experiments/context_feature_coverage.csv) | 核对原始数据一致性和新增特征覆盖率 |
| 训练检查 | [共用训练参数](experiments/training_parameters.json) | 查看控制变量和配置对照结果 |
| 筛选 | [筛选指标](experiments/selection_metrics.json)、[锁定决定](experiments/selection_decision.json) | 查看2023–2024年消融结果及选择依据 |
| 确认 | [确认指标](experiments/confirmation_metrics.json)、[日配对统计](experiments/paired_diagnostics.csv)、[环境诊断](experiments/regime_metrics.csv) | 查看2025–2026年结果、增量区间及环境表现 |
| 模型诊断 | [特征重要性](experiments/selected_feature_importance.csv) | 查看选定模型的gain和split次数 |
| 执行追踪 | [完整任务表](EXPERIMENT_PROCESS.md#3-正式任务执行记录) | 查看任务时间、Task ID和Run ID |

完整提交响应、状态、原始日志、日级Parquet及作废运行留在本地归档，不随仓库提交。执行过程文档保留了这些记录的用途、任务标识和异常处理。新实验应创建独立记录，避免复用本次任务句柄。

## 4. 实现索引

| 文件 | 职责 |
| --- | --- |
| [插件注册](axonx_alpha158_enhanced/plugin.yaml) | 注册ETL、因子分析、训练、预测和回测任务 |
| [横截面特征计算](axonx_alpha158_enhanced/internal/cross_section.py) | 26个特征的名称、分组、计算逻辑和时点协议 |
| [ETL](axonx_alpha158_enhanced/etl.py) | 合并原始158特征与新增特征，输出数据集和每日环境诊断 |
| [训练](axonx_alpha158_enhanced/training.py) | 选择特征组、内部验证、最终拟合及模型产物 |
| [预测](axonx_alpha158_enhanced/predict.py) | 按训练metadata中的特征顺序生成样本外预测 |
| [回测](axonx_alpha158_enhanced/backtest.py) | 评估TopN组合并输出日级及分期指标 |
| [特征验证测试](tests/test_cross_section.py) | 验证因果性、历史分组及原始特征契约 |

## 5. 特征组

| 训练参数分组 | 新增数量 | 内容 |
| --- | ---: | --- |
| `market` | 11 | 市场收益均值/中位数、上涨占比、收益IQR、涨跌停比例、5/20日趋势、标准化冲击、放量和成交金额集中度 |
| `liquidity` | 6 | 截至T−1的成交金额排名、个股放量、低/高成交金额组收益、组间收益差及5日均值 |
| `relative` | 5 | 相对市场/成交金额组收益、当日收益排名、5/20日相对趋势 |
| `interaction` | 4 | 市场冲击/下跌幅度×相对收益、金额组价差×金额排名、市场放量×个股放量 |

完整名称与计算口径见[横截面特征计算](axonx_alpha158_enhanced/internal/cross_section.py)；ETL metadata记录 `context.feature_groups` 和时点协议。收益使用相邻交易日复权收盘；相邻日行情缺失时，不将跨停牌期收益混为一天收益。

增强ETL一次生成184个特征，下游通过 `--context-groups` 选择所需组：`none` 保留原始158个特征，`market` 保留169个，`market,liquidity,relative` 保留180个，四组全开保留184个。原始特征名称保持 `f_alpha158_*`，新增名称为 `f_context_*`。

## 6. 远程运行与复现

在仓库根目录执行，将 `<host:port>` 替换为目标AxonX服务。按服务要求配置凭据，准备与计划一致的Tushare分区数据：

```bash
.venv/bin/axonx plugin install plugins/a158_enhanced --target '<host:port>'
.venv/bin/axonx submit --task a158e_etl --start-date 20150101 --target '<host:port>'
```

每次提交后记录实际返回的Task ID和Run ID，等待任务成功再提交下游：

```bash
.venv/bin/axonx wait_task --task-id '<task_id>' --run-id '<run_id>' \
  --client-timeout 86400 --target '<host:port>'
```

使用成功ETL的实际Task ID提交训练：

```bash
.venv/bin/axonx submit --task a158e_train --source-tasks '<etl_task_id>' \
  --context-groups market,liquidity,relative,interaction --train-start 20150101 --train-end 20230101 \
  --target '<host:port>'
```

按[实验计划](DEVELOPMENT_PLAN.md)从同一ETL分别训练 `none`、`market`、`market,liquidity,relative` 和四组完整方案。固定数据快照、训练区间、模型参数、费用与随机种子。

先运行筛选期预测和回测，按计划锁定组合：

```bash
.venv/bin/axonx submit --task a158e_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20241231 --target '<host:port>'
.venv/bin/axonx submit --task a158e_backtest --source-tasks '<predict_task_id>' --target '<host:port>'
```

仅对基线和锁定方案再运行确认期，预测参数为 `--pred-start 20250101 --pred-end 20260930`。记录完整配置、模型、预测、回测汇总和日级产物；数据快照不同的实验结果应另行报告。

本次本地恢复/报告脚本绑定了特定服务及既有任务，不随仓库提交。上述CLI流程使用新生成的真实句柄，可用于在自己的目标服务重跑协议。

## 7. 本地验证

```bash
PYTHONPATH=plugins/a158_enhanced .venv/bin/python -m pytest \
  plugins/a158_enhanced/tests/test_cross_section.py \
  tests/unit/test_alpha158_labels.py tests/unit/test_alpha158_backtest.py -q
```

检查未来数据因果性、原始特征契约、当天放量对历史分组的影响、停牌、平值、历史不足和统计池独立于标签/可买性。回测沿用原插件的日线成交代理，扣费Sharpe由日净收益另行计算，区别于原回测产物中的gross Sharpe。
