# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 的主实验版在 Alpha158 的 158 列上增加两个个股风险因子：20 日残差波动与下行风险，训练使用 160 列。ETL 还提供可选的全局均值、方差和中性动量因子，共发布 171 列；本文复现命令只选择 `risk` 组。

训练继承基础插件的截止日隔离、末尾 10% 日期早停与全训练期重拟合。预测和普通回测复用基础插件。

## 因子与时点

| 分组     | 特征数 | 定义                                         |
| -------- | -----: | -------------------------------------------- |
| mean     |      4 | 各窗口收益截面缩尾均值，反映市场整体涨跌方向 |
| variance |      4 | 各窗口收益截面缩尾样本方差，反映股票涨跌分歧 |
| neutral  |      3 | 5/10/20 日 beta 调整动量                     |
| risk     |      2 | 20 日特质波动与下行风险                      |

每只股票收益为复权 C(T)/C(T−h)−1，h=1/3/5/10 个市场交易日。两个端点须有报价且成交量、成交额和复权价格为正；包含涨跌停股票，不使用未来标签或可交易性筛选。各日期、各窗口独立用 2%/98% 线性分位缩尾，参考 Axon2 的全局特征实现，再计算等权均值与样本方差（ddof=1）。空股票池保留缺失，单股票方差缺失。方差描述截面分歧；均值接近零并不能单独证明多数股票震荡。

全局矩在 T 收盘后可用，同日所有股票共享相同值；动量/风险因子随股票变化。全局矩不能用单因子截面 IC 判断，应比较模型消融。定义见 [cross_section.py](axonx_qlib_factor/internal/cross_section.py)；ETL 保存各窗口样本数和每日因子值。

`context_groups` 接受逗号分隔的 `mean`、`variance`、`neutral`、`risk`，或 `none`。默认仍为 `none`；本文因子版显式使用 `risk`。不支持的组名和上下文特征列会在校验时报错。

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
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups risk --feature-fraction 1.0 --target http://research.example:1024
axonx submit --task qlib_factor_predict --source-tasks '<train_task_id>' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx submit --task qlib_factor_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --transaction-cost-rate 0.001 --target http://research.example:1024
```

每次保存返回的 Task ID 和 Run ID，等待 `succeeded` 后再提交下游。`qlib_factor_analysis` 是可选的因子分析分支。通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更仍要求重启。基础数据准备、标签与成交口径见 [Qlib Alpha158](../qlib_a158/README_ZH.md)。

<a id="experiments"></a>

## 最终实验设定与结果

本节记录本插件的最终实验；跨插件对比见[三个版本实验对比](../../docs/zh/research/experiments.md#comparison)。指标整理自 45 机器成功任务的 metadata、summary.parquet、daily.parquet 和 trades.parquet，原始产物保留在执行工作区。

### 本版本配置

158 个基础特征加两个 risk 因子；context_groups=risk、feature_fraction=1.0；固定 holding_days=1。

数据、训练窗口、样本过滤、成交与费用共同设定见[三个版本实验对比](../../docs/zh/research/experiments.md#comparison)。

本次模型使用 160 个特征，早停选择 426 轮后全训练期重拟合，内部验证 RankIC 为 0.11321。

最终 stock_risk 只增加 `f_context_residual_vol20`、`f_context_downside_risk20`，不使用全局均值/方差或 neutral 列。`context_windows=[10]` 是该模型保存的训练配置，仅过滤全局因子，因此对 risk 组无影响。个股日收益按当日横截面 2%/98% 线性分位缩尾；市场收益为同截面的缩尾等权均值。beta 使用截至 T−1 的 60 个市场日、至少 30 个有效成对收益，以协方差/市场方差估计并截断至 [−3,3]；市场方差 ≤1e−12 时缺失。残差日收益为个股缩尾收益 − 历史 beta × 市场收益，20 日残差波动用样本标准差（ddof=1）；下行风险为 sqrt(mean(min(缩尾日收益,0)²))。两者要求 20 日内至少 16 个有效值，缺失/未定义保持缺失。

context_groups=risk，context_windows=[10]，固定持有期 holding_days=1；当前插件默认 context_groups 仍为 none。

### 指标口径

信息系数／秩信息系数、净收益、夏普比率、换手与基准超额的统一定义见[实验对比](../../docs/zh/research/experiments.md#comparison)。组合指标使用 909 日；基准超额使用共同有效的 908 日。

### 整体信号与 Top20 完整结果

| 指标                              | 风险因子增强 |
| --------------------------------- | -----------: |
| 整体信息系数（IC）                |       0.0545 |
| 整体秩信息系数（RankIC）          |       0.0966 |
| 整体秩信息比率（RankICIR，年化）  |      14.2859 |
| 净年化收益                        |        9.04% |
| 净累计收益                        |       36.64% |
| 净夏普比率                        |       0.4054 |
| 净年化波动率                      |       28.53% |
| 最大回撤                          |      -40.67% |
| 日收益胜率                        |       53.47% |
| 日均双边换手                      |      199.35% |
| 日均费用 / 前日权益               |      0.1993% |
| 已完成交易                        |       18,079 |
| 相对市场均值的净超额年化收益      |       -1.86% |
| 相对市场均值的净信息比率          |      -0.0649 |
| 相对市场均值的净超额最大回撤      |      -21.71% |
| 相对沪深 300 代理的净超额年化收益 |        4.09% |
| 相对沪深 300 代理的净信息比率     |       0.2947 |
| 相对沪深 300 代理的净超额最大回撤 |      -29.34% |

### Top30 结果

| 方案         | 净年化收益 | 净夏普比率 | 最大回撤 | 日均双边换手 | 相对市场均值的净信息比率 | 相对沪深 300 代理的净信息比率 |
| ------------ | ---------: | ---------: | -------: | -----------: | -----------------------: | ----------------------------: |
| 风险因子增强 |      4.27% |     0.2480 |  -41.41% |      199.37% |                  -0.4236 |                        0.0840 |

### Top20 分年结果

| 年份 | 交易日数 | 风险因子增强 |
| ---- | -------: | -----------: |
| 2023 |      242 |      -10.08% |
| 2024 |      242 |       10.54% |
| 2025 |      243 |       56.68% |
| 2026 |      182 |      -14.73% |

各年值为对应区间净年化；2026 年截至 10 月 8 日。结果为 `incomplete_market_data`，缺报价可能延迟退出并沿用旧估值，同收盘成交为代理假设。

### 复现实验

每阶段保存返回的 Task/Run ID 并等待成功后再提交下游；远程执行时统一使用同一 `--target`。以下参数与 实验设定一致，其余默认值提交前用 `get_task_definition` 核对。

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

| 阶段／方案       | 任务标识                                       | 运行标识                           |
| ---------------- | ---------------------------------------------- | ---------------------------------- |
| 风险因子训练     | `train#qlib_factor_train#2026100917VGxi`       | `d55e035ab9c549ab840770b1e8444f10` |
| 风险因子预测     | `predict#qlib_factor_predict#2026100917Z7Ys`   | `1a033666806b4e359c6acc11f8b02399` |
| 风险因子增强回测 | `backtest#qlib_factor_backtest#2026100917v6ku` | `37cf5867c5d344da9c4b6a9b56bc6e24` |

| 输入     | SHA-256                                                            |
| -------- | ------------------------------------------------------------------ |
| market   | `5240ca57a6ba0f045679c0661d2785bbb9c793e7bd5f4c1091d7998061e98b32` |
| calendar | `cb40f3148a2ff06ff4ad1ace95ed1a8e4da5c45f844007562dbc8020aa2b15a5` |
| labels   | `39e1cabc39f5b6050a13c3a015a7d3b0c7912a80fbf285c2a093427ddff4ba3f` |
| input    | `cdb9eac261b18e85de008558f7ad4524b214ce72bd8fcf4e101492eda2a36f06` |

框架/插件版本为 0.1.1 / 0.2.0；Python 3.12.14、Polars 1.44.2、LightGBM 4.7.0。新数据不保证重现未发布的历史快照；原始运行产物不随仓库提交。
