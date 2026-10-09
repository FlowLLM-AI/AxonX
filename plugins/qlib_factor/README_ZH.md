# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 基于 `qlib_a158` 提供横截面环境因子研究。保留 158 个基础特征，增加市场、流动性、相对表现和交互四组共 26 个特征；ETL 发布 184 个特征，模型按 `context_groups` 选择。

训练默认使用 `label_return_rank` 和 `parameter_preset=axonx`，继承训练截止日隔离、末尾 10% 日期早停和全训练期重拟合。预测与普通回测复用基础插件，策略决策由 `qlib_strategy` 提供。

## 因子与时点

| Group       | Features |
| ----------- | -------: |
| market      |       11 |
| liquidity   |        6 |
| relative    |        5 |
| interaction |        4 |

因子定义见 [cross_section.py](axonx_qlib_factor/internal/cross_section.py)。成交金额分组使用截至 T−1 的历史；当日市场信息在收盘后可用。收益使用相邻市场日复权报价，缺行情保留缺失；计算只使用行情与当日状态。ETL 保存特征组、时点协议、覆盖率与每日环境诊断。

`context_groups` 接受逗号分隔的组名，`none` 仅使用基础特征。默认组为 `liquidity`，共 164 个模型特征，按训练期内部验证 RankIC 选择。

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
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

每次保存返回的 Task ID 和 Run ID，等待 `succeeded` 后再提交下游。`qlib_factor_analysis` 是可选的因子分析分支。使用此源码仓库的核心时，通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更，以及不支持插件导入刷新的旧核心仍要求重启；执行环境须具备分侧费用支持。基础数据准备、标签与成交口径见 [Qlib Alpha158](../qlib_a158/README_ZH.md)。

## 实验与复现

![Signal quality](../../docs/figures/benchmark/qlib-signal-quality.svg)

[实验方案](DEVELOPMENT_PLAN.md)定义 15 个非空组组合及无增强对照。训练 `[20150101,20230101)`，从 `20230101` 起预测，买入 0.05% / 卖出 0.15%。按训练期内部验证 RankIC 锁定增强组，再报告共同样本外窗口的全部候选表现。

[完整结果](EXPERIMENT_RESULTS_ZH.md) · [执行与核对](EXPERIMENT_PROCESS.md) · [指标索引](experiments/README_ZH.md) · [三层对照](../qlib_a158/THREE_LAYER_EXPERIMENTS_ZH.md)。
