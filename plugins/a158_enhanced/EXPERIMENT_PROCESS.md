# 横截面环境增强版实验执行过程

执行日期：2026-10-02。执行目标：用户指定的远程 AxonX 服务（地址仅保存在本地配置）。下表时间统一转换为北京时间（Asia/Shanghai）；Task ID、Run ID和状态来自保存的服务响应。

计划见 [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)，数值结果和局限见 [EXPERIMENT_RESULTS.md](EXPERIMENT_RESULTS.md)。本文件记录实施、检查、异常处理、实验执行与方案锁定过程。

## 1. 实验准备与实现

1. 阅读仓库 harness skill 和原始 a158 的ETL、训练、预测、回测实现。确认原插件为LightGBM，已有Top1/2/3/5/10/15/20/30评估。
2. 本轮不扩展下载器接入 daily_basic，使用已有 daily.amount 构造交易活跃度分组；这些分组不解释为大小市值。
3. 在 plugins/a158_enhanced 建立独立副本，隔离发行包、Python包、插件入口和Task注册名，先写开发计划。
4. 检查远程资源、已安装插件和成功基线任务。目标机器128逻辑核，初查可用内存约714GB；原始ETL覆盖2015-01-05至2026-09-30。
5. 开发26个候选特征：market 11个、liquidity 6个、relative 5个、interaction 4个。ETL统一产出184个特征，下游按组选择，同一数据集支持全部消融。
6. 固定训练期2015–2022、筛选期2023–2024和确认期2025至2026-09-30。筛选门槛为RankIC及Top10/20净年化收益均高于基线，合格方案中选择RankIC最高者。确认期不继续调参。

## 2. 开发验证与异常处理

- 本地构建环境缺少pip，补齐后成功构建wheel和安装远程插件。
- 首次复制误将原始特征前缀改为 f_alpha158e_*。兼容性检查发现后恢复 f_alpha158_*，添加原始特征契约测试；取消对应三组增强训练并归档旧运行。旧增强ETL作废，不参与正式比较。原始基线预测使用原始数据和模型，不受此问题影响，可以复用。
- 通过21项相关测试，覆盖未来数据改写/截断不影响历史特征、当天金额突增不改变历史分组、统计池不依赖未来标签/可买性、停牌、平值、历史不足、非有限值，以及原有标签和回测测试。静态检查通过。
- 正式增强ETL成功后，在远程逐值对照所有原始字段：11,441,741行、179个原始字段完全一致。新增特征有限值覆盖率98.57%–100%，NaN和Inf均为0。
- 三组增强训练的日期、标签、尾部过滤、模型超参数和随机种子逐项核对与基线一致。允许差异为任务名称、ETL来源和特征组；各模型的早停轮数由同一内部验证规则决定。

检查证据：

- [原始数据逐值对照](experiments/baseline_data_parity.json)
- [训练参数对照](experiments/training_parameters.json)
- [特征覆盖率](experiments/context_feature_coverage.csv)
- [测试代码](tests/test_cross_section.py)

## 3. 正式任务执行记录

仅使用 succeeded 上游提交下游。各任务使用自动生成名称；脚本保留实际Task ID和Run ID，轮询时核对Run ID。以下均为正式实验中的成功任务，不包含作废运行。

| 阶段 | Task ID | Run ID | 开始时间 | 完成时间 | 状态 |
| --- | --- | --- | --- | --- | --- |
| selection_baseline_predict | `predict#a158e_predict#2026100217tMyM` | `a6ea8b7b843a4f9ab97456a820268bdc` | 2026-10-02 17:08:53 | 2026-10-02 17:09:01 | succeeded |
| etl | `etl#a158e_etl#202610021764NJ` | `f141857a4ece4112aac09cc900249282` | 2026-10-02 17:09:54 | 2026-10-02 17:12:03 | succeeded |
| relative_train | `train#a158e_train#2026100217EBSh` | `26754b254ad84e00bc74741a26083cbd` | 2026-10-02 17:12:32 | 2026-10-02 17:18:26 | succeeded |
| market_train | `train#a158e_train#2026100217rlZh` | `6cc52d18731343b695c099fd70dd12d5` | 2026-10-02 17:12:32 | 2026-10-02 17:19:30 | succeeded |
| all_train | `train#a158e_train#20261002173FIq` | `e1df9f8013ff4e079a2f2ee5c7eb1cda` | 2026-10-02 17:12:32 | 2026-10-02 17:19:59 | succeeded |
| selection_baseline_backtest | `backtest#a158e_backtest#2026100217HfAY` | `8a5efd94f34d4be2aad76eb9c0c2a9de` | 2026-10-02 17:12:34 | 2026-10-02 17:12:43 | succeeded |
| selection_relative_predict | `predict#a158e_predict#2026100217Oxka` | `09b2956e683e42b8bfae1cfb62c7ccd1` | 2026-10-02 17:18:34 | 2026-10-02 17:18:38 | succeeded |
| selection_relative_backtest | `backtest#a158e_backtest#2026100217yfa6` | `1fe85341b2494ac797a804a335dd92ba` | 2026-10-02 17:18:55 | 2026-10-02 17:18:58 | succeeded |
| selection_market_predict | `predict#a158e_predict#2026100217Qk6T` | `ec5999327db44c67937e18a56f32adc7` | 2026-10-02 17:19:37 | 2026-10-02 17:19:41 | succeeded |
| selection_market_backtest | `backtest#a158e_backtest#20261002176LLQ` | `48d2a0b8185b4a409ef7d02ddf7a254d` | 2026-10-02 17:19:59 | 2026-10-02 17:20:01 | succeeded |
| selection_all_predict | `predict#a158e_predict#2026100217YAHA` | `6f6e8a5b079e42b4a62250e60fdcf634` | 2026-10-02 17:20:18 | 2026-10-02 17:20:22 | succeeded |
| selection_all_backtest | `backtest#a158e_backtest#2026100217miW7` | `8e4b28da3bc2433691ce12c53b9c4de2` | 2026-10-02 17:20:42 | 2026-10-02 17:20:44 | succeeded |
| confirmation_all_predict | `predict#a158e_predict#2026100217lNgr` | `17efdd88b2554316b31668dca3c552f4` | 2026-10-02 17:21:12 | 2026-10-02 17:21:16 | succeeded |
| confirmation_baseline_predict | `predict#a158e_predict#2026100217rwvR` | `29db199eba044021bc03696c39876202` | 2026-10-02 17:21:12 | 2026-10-02 17:21:16 | succeeded |
| confirmation_all_backtest | `backtest#a158e_backtest#2026100217bly1` | `b906fc2ef9954c7aafa64a2803110157` | 2026-10-02 17:21:35 | 2026-10-02 17:21:37 | succeeded |
| confirmation_baseline_backtest | `backtest#a158e_backtest#2026100217jMS6` | `bac665bcbe0349358327ef98cd3dcb98` | 2026-10-02 17:21:35 | 2026-10-02 17:21:37 | succeeded |

基线训练复用已成功任务 `train#a158_train#2026100216aScx`（Run ID `89343e06ed814e06aef66998b8109d63`），并核对配置；未为本次实验重复训练基线。

完整配置、各步骤进度及产物路径保存在对应 `experiments/*_status.json`；提交响应保存在 `*_submit.json`。

## 4. 模型训练与筛选

| 方案 | 特征数 | 最佳轮数 | 模型来源 |
| --- | ---: | ---: | --- |
| baseline | 158 | 362 | `train#a158_train#2026100216aScx` |
| market | 169 | 403 | `train#a158e_train#2026100217rlZh` |
| relative | 180 | 284 | `train#a158e_train#2026100217EBSh` |
| all | 184 | 385 | `train#a158e_train#20261002173FIq` |

完成四个方案的2023–2024预测和回测后，写出筛选指标。market、relative、all均满足三项主指标门槛，all的RankIC最高（0.0974），因此锁定全部四组方案；Top10/20净年化分别为18.38%/12.05%。
锁定后只对baseline与all运行2025–2026确认期，没有在查看确认期结果后更换组合、调参或增加候选实验。

- [筛选期完整指标](experiments/selection_metrics.json)
- [锁定决定及规则](experiments/selection_decision.json)

## 5. 最终确认与结果整理

确认期baseline和all的预测及回测均成功。all的RankIC和Top10/20净年化收益点估计高于基线，最大回撤减小；但Top1–3收益下降。日配对增量的95%区块bootstrap区间包含零。
结果整理包括：完整消融表、分年结果、确认期全部TopN、信号日市场涨跌环境下RankIC/NDCG、20交易日区块bootstrap、环境特征模型gain排名和原始回测口径限制。gain排名只表示模型使用程度，不证明每个特征独立有效。

- [完整结果报告](EXPERIMENT_RESULTS.md)
- [确认期指标](experiments/confirmation_metrics.json)
- [配对差异及区间](experiments/paired_diagnostics.csv)
- [市场环境诊断](experiments/regime_metrics.csv)
- [选定模型重要性](experiments/selected_feature_importance.csv)

## 6. 最终安装与入口验证

将已锁定完整方案设为增强版默认配置，安装版本0.1.2。安装时发现远程服务缓存已导入的旧train模块，定义查询仍显示旧默认分组；将 a158e_train 注册到独立 training.py，并同步包导出，完成本地导入和测试检查。
最终同时检查服务schema和远程全新Python进程：两者默认均为 market,liquidity,relative,interaction，新进程解析入口为 axonx_alpha158_enhanced.training，安装版本0.1.2。原始插件、已有任务和实验产物均保留。此阶段只调整默认值、模块入口和说明，没有改变已评估的特征计算、训练超参数或回测逻辑，也未新增确认期调参。

最终安装响应、服务定义和新进程验证响应分别保存在本地归档的 `experiments/plugin_install_final.json`、`train_definition_final.json` 和 `fresh_runtime_verification.json`，不随仓库提交。

## 7. 作废记录与复现入口

作废记录保留在 本地 `experiments/superseded_feature_namespace/`。首次增强ETL完成但因原始特征命名错误被排除；对应三组训练取消响应均已保存，未用于筛选或确认。

| 作废阶段 | Task ID | Run ID | 处理 |
| --- | --- | --- | --- |
| all_train | `train#a158e_train#2026100217RRxY` | `c63080de3c7941c08721902c95da4ad7` | 已取消，不参与正式实验 |
| etl | `etl#a158e_etl#202610021733OC` | `91fb731c7e364d5392c8a3f70e28e6d2` | 作废，改正前缀后重跑 |
| market_train | `train#a158e_train#2026100217VVvo` | `e3269bc7954042bdb47a0f2b1bd28636` | 已取消，不参与正式实验 |
| relative_train | `train#a158e_train#202610021708YR` | `fb054e75760a468ab0712c29e47407a8` | 已取消，不参与正式实验 |

运行过程原始日志保存在本地 `experiments/research.log`。本地 `scripts/research.py`、`scripts/report.py` 仅用于恢复本次运行和整理报告，不随仓库提交。通用重跑命令见 [README.md](README.md)，使用新生成的真实句柄开展独立实验。

本文件根据已保存的响应和日志整理，不补造未保存的时间或额外实验。原始配置、提交记录、成功状态和日级Parquet保存在本地 `experiments/` 归档中；仓库仅提交可阅读的指标和校验汇总，见 [材料索引](experiments/README.md)。
