# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 继承 `qlib_factor` 和 `qlib_a158`，在同一预测上研究持仓策略。框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。不提供固定到期参数，`planned_exit_date` 为空。

## 安装与执行

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx plugin install plugins/qlib_strategy --target http://research.example:1024
axonx submit --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

可复用成功的基础或增强预测。提交后保存 Task / Run ID，等待成功再读取结果。上游 `qlib_strategy_etl`、`qlib_strategy_analysis`、`qlib_strategy_train`、`qlib_strategy_predict` 注册因子层实现；策略比较直接复用已有预测。通过远程安装 Job 更新仅贡献 Task 的 wheel 无需重启；按 `restart_required=true` 重启并核对 Task 定义。直接 pip/源码变更仍要求重启；核心与插件使用同一源码仓库版本。

## 实验记录

历史实验设置、完整结果与产物来源统一见[研究实验指南](../../docs/zh/research/experiments.md#comparison)。这些历史记录不代表当前代码已重新运行验证。
