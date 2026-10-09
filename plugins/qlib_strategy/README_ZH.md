# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 继承 `qlib_factor` 和 `qlib_a158`，在同一预测上研究持仓策略。框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。关闭固定到期退出，`holding_days=1`，`planned_exit_date` 为空。

## 安装与执行

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx plugin install plugins/qlib_strategy --target http://research.example:1024
axonx submit --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --minimum-holding-days 10 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

可复用成功的基础或增强预测。提交后保存 Task / Run ID，等待成功再读取结果。上游 `qlib_strategy_etl`、`qlib_strategy_analysis`、`qlib_strategy_train`、`qlib_strategy_predict` 注册因子层实现；策略比较直接复用已有预测。使用此源码仓库的核心时，通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更，以及不支持插件导入刷新的旧核心仍要求重启；核心须支持 `portfolio_policy` 和分侧费用。

## 实验结果

在基础预测和按内部验证选定的增强预测上，分别比较最短持有 0/5/10/15/20/30 日，共 12 组回测；主方案预先固定为 10 日、每日每侧 20% 数量上限。候选结果用于观察持有期影响，不根据 2023 年后收益重新挑选主方案。

[完整结果](EXPERIMENT_RESULTS_ZH.md) · [指标索引](experiments/README.md) · [三层对照](../qlib_a158/THREE_LAYER_EXPERIMENTS_ZH.md)。缺行情不自动视为停牌；涉及缺报价的结果为 `incomplete_market_data`。
