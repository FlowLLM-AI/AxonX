---
title: 回测结果解读
description: 统一股票协议、截止安全标签、逐日估值和持仓产物。
---

# 回测结果解读

Alpha158 和增强 Alpha158 共用 `BaseStockBacktestTask` 和持仓账本。股票协议版本 2 将信号时特征、固定期限标签和行情分开存储。

共享实现位于 `axonx.task.builtins.stock`，新插件应从该包导入。

## 数据契约

ETL 发布四份独立产物：

| 产物       | 含义                                                     |
| ---------- | -------------------------------------------------------- |
| `dataset`  | 信号时特征、选股资格、参考价格和复权因子                 |
| `labels`   | 固定次一市场日同一时点的原始小数收益、目标日期及可用状态 |
| `market`   | 独立行情、复权因子、买卖代理和市场状态                   |
| `calendar` | 市场交易日，包括没有有效预测的日期                       |

主键为 `trade_date`（YYYYMMDD 字符串）、`trade_time`（HHMM 字符串）、`ts_code`。标签不能删除特征行或预测候选。停牌只使对应固定期限标签无效，不以复牌后的收益替代。训练在排除截止时间之后的标签、选定有效样本并处理尾部后计算 rank/CSZ，拟合和验证分别使用自身参考样本。

`market_status` 为 `quoted`、`suspended` 或 `missing_data`。ETL 可读取独立的 `market_status_file`，其字段为主键及确认的停牌／缺失状态。缺行情不能自动推断为停牌。信号当天确认停牌或缺失时，即使有残留报价也会关闭信号可买标记，模型候选行仍保留。

## 输入

预测 Parquet 的必需列、可选列和 metadata 要求见[预测到股票回测的输入契约](../reference/research-artifacts.md#预测到股票回测的输入契约)。

```bash
axonx submit --task qlib_a158_backtest --source-tasks '<Predict Task ID>' \
  --top-ns '[1,5,10,30]' --holding-days 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

来源任务自动解析行情、日历和标签产物。指定文件时使用 `input_file`、`market_file`、`calendar_file` 和可选 `labels_file`。`as_of_date` 为包含当天的评价截止日期，默认取行情最后日期。`top_ns` 是整数列表，各组合独立记账。日历日期必须是有效 YYYYMMDD，不能有空值或重复；计算标签期限和持有期前会拒绝非法日历。

| 参数                            | 默认值   | 含义                         |
| ------------------------------- | -------- | ---------------------------- |
| `holding_days`                  | `1`      | 按市场日计算的计划持有期     |
| `buy_cost_rate`                 | `0.0005` | 买入成交金额费用率           |
| `sell_cost_rate`                | `0.0015` | 卖出成交金额费用率           |
| `annual_risk_free_rate`         | `0.012`  | 年无风险收益率               |
| `annualization_days`            | `252`    | 年交易日数                   |
| `minimum_index_weight_coverage` | `0.98`   | 指数权重收益代理的覆盖率要求 |
| `index_codes`                   | `[]`     | 可选的信号候选指数限制       |

默认与 Qlib 参考配置一致： `--buy-cost-rate 0.0005 --sell-cost-rate 0.0015`，即买入 0.05%、卖出 0.15%。显式设为 `0` 表示该侧免费。费用按实际成交金额收取，归一化资金回测不设最低金额费用。

## 成交与估值

信号按分数降序、代码升序排名，选股不使用未来标签。引擎先更新已有持仓估值，尝试卖出到期持仓，再用可用现金买入当日目标。目标无法成交时不补入低分股票；已有同股票持仓、持仓容量和可用资金都会约束买入。

无法卖出时保留持仓和资金占用。确认停牌沿用上一可靠复权估值，后续有行情时更新估值并再次尝试退出。已持有或选中的股票缺少可靠数据时，返回 `evaluation_status=incomplete_market_data`，仍可检查暂定结果。评价截止时不强制清仓。

同一时点价格是成交代理，不保证在完整 bar 或收盘行情形成后计算出的信号能够按该价格成交，也不模拟排队和部分成交。应先阅读产物中的执行协议，再解释策略可交易性。

```text
Equity = cash + marked position value
Daily net return = equity / previous equity - 1
Daily cost = executed buy and sell costs / previous equity
Daily gross return = daily net return + daily cost
Turnover = executed buy and sell notional / previous equity
```

持仓使用复权价格单位处理公司行为引起的价格变化，退出时不重复确认已经体现在估值中的收益。初始买入和后续实际成交均收费。

## 输出

| 产物        | 含义                                             |
| ----------- | ------------------------------------------------ |
| `daily`     | 按交易日历排列的收益、权益、现金、持仓及信号诊断 |
| `summary`   | 总体、年度、季度和月度统计                       |
| `targets`   | 信号目标候选                                     |
| `orders`    | 实际成交与未成交原因                             |
| `positions` | 每日实际持仓、复权单位、权重和市值               |
| `trades`    | 已完成持有期的实际买卖价格、收益和费用           |

`daily` 使用 `topN_*` 列，`dimensions` 声明组合规模和基准。`top30_holdings` 是信号目标列表，不是实际持仓；真实敞口见 `positions`。尚未退出的持仓仍保留在该产物中，即使没有已完成交易。

## 信号诊断与基准

IC、RankIC、NDCG 与目标选股共用信号当天可买候选池，包括 `index_codes` 限制。IC 和 RankIC 对比预测分数与有效的固定次一市场日原始收益。NDCG 对比高分信号和相同可用收益样本的排序质量；缺标签不会补入低分候选。这些指标属于信号日期，持仓收益和估值属于组合日历日期。

`benchmark_universe_return` 是可用信号横截面的平均收益。`index_weight_*` 只有覆盖率达标时才生成加权收益代理，它们不是官方全收益指数。基准收益按标签目标日期排列，与组合估值周期对齐。

Studio 读取 `daily`、`summary`、`dimensions`。净收益图复合每日净收益，累计毛收益图相加每日毛收益，因此后者不必等于汇总表中的复合毛收益。期间统计由任务生成，移动图表日期范围不会自动重新回测。

Studio 根据 `dimensions.top_ns` 生成收益和 NDCG 曲线，将行情不完整的评价标为暂定结果，并展示全部组合产物。预测统计只描述信号时分数和选股资格；协议版本 2 的预测不嵌入未来收益或有效收益覆盖率。统计为空或标签缺失时显示不可用。
