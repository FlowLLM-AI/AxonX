# Alpha158 Strategy

[English](README.md) · [简体中文](README_ZH.md)

`a158_strategy` 继承 `a158_factor`（间接继承 `a158`），复用因子、模型和预测，只优化持仓。框架统一处理估值、现金、费用、订单、持仓和成交产物。

## 简单策略

- 仍在 TopN 的持仓继续保留。
- 持有至少 10 个市场日后，优先卖出排名最差且已离开 TopN 的股票。
- 每天每侧最多成交 `max(1, floor(N × 20%))` 只：Top5/10/20/30 为 1/2/4/6 只。首次建仓豁免；这是股票数量上限，持仓权重漂移后交易金额可能超过 20%。
- 缺行情或不可卖继续占用资金；先卖后买，买入失败不补位。新仓最多分配 1/N 权益，已有仓位不再平衡。截止日不强制卖出。

参数：`replacement_fraction=0.2`、`minimum_holding_days=10`、`rank_buffer=1`。固定到期卖出关闭，`holding_days` 只能为 1；持仓 `planned_exit_date` 为空，`exit_delayed` 不用于衡量排名退出延迟。

## 提交

安装需要框架的 `portfolio_policy` 扩展，部署当前源码后执行：

```bash
axonx plugin install plugins/a158_strategy --target http://research.example:1024
axonx submit --task a158s_backtest --source-tasks '<factor_predict_task_id>' --top-ns '[5,10,20,30]' --as-of-date 20261008 --target http://research.example:1024
```

`a158s_etl`、`a158s_factor`、`a158s_train`、`a158s_predict` 注册因子层实现；比较策略时直接复用成功的因子层预测，避免重复训练改变控制变量。配置、Task／Run ID、输入和结果见[三层实验](../a158/THREE_LAYER_EXPERIMENTS_ZH.md)。

选择依据为基线预测上的 150 组探索性策略实验；它不构成独立检验。缺报价沿用旧估值的结果标记 `incomplete_market_data`，均为暂定。
