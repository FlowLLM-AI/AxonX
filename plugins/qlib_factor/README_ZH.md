# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 为 Alpha158 ETL 增加 13 个可选的市场矩、中性动量和风险特征，共输出 171 个特征列。训练按组选择，默认 `none` 使用 158 个基础特征。下方示例选择 `risk`，共 160 个特征。

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

Beta 使用 T−1 及之前 60 个市场日，至少需要 30 个股票与市场配对收益。股票日收益按当日 2%/98% 分位缩尾，市场收益为其等权均值。Beta 为协方差除以市场方差，并限制在 [−3,3]；方差 ≤1e−12 时保持空值。中性动量为股票 5/10/20 日累计收益减去历史 beta × 市场累计收益。残差波动为“股票日收益 − 历史 beta × 市场日收益”的 20 日样本标准差；下行风险为 sqrt(mean(min(股票日收益,0)²))。风险窗口至少需要 20 日内 16 个有效观测；当日行情无效时所有股票特征保持空值。

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
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

每次保存返回的 Task ID 和 Run ID，等待 `succeeded` 后再提交下游。`qlib_factor_analysis` 是可选的因子分析分支。通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更仍要求重启。基础数据准备、标签与成交口径见 [Qlib Alpha158](../qlib_a158/README_ZH.md)。

## 实验记录

历史实验设置、完整结果与产物来源统一见[研究实验指南](../../docs/zh/research/experiments.md#comparison)。这些历史记录不代表当前代码已重新运行验证。
