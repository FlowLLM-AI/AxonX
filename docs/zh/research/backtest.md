---
title: 回测结果解读
description: 统一股票协议、截止安全标签、逐日估值和持仓产物。
---

# 回测结果解读

Alpha158 和增强 Alpha158 共用 `BaseStockBacktestTask` 和持仓账本。ETL 将信号时特征、固定期限标签和行情分别发布为独立产物。

共享实现位于 `axonx.task.builtins.stock`，新插件应从该包导入。

![独立信号、市场输入、真实持仓与组合报告](../../figures/research/backtest-accounting.svg)

## 数据契约

![Studio 0.3.0 backtest universe, overall metrics and Top N summary](../../figures/studio/backtest-overall.png)

[查看高清原图](../../figures/studio/backtest-overall.png)

完整截图展示 Playground 合成回测的 **总体** 标签页，指标用于说明界面，不是 Alpha158 结果。

Studio 回测页优先展示组合选择器和报告，报告下方保留产物清单，每份发布文件仅在清单中列出一次。

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
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<Predict Task ID>"]' --top-ns '[5,10,30]' --holding-days 1
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<Portfolio Task ID>"]' --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

先构建 Portfolio，再运行 Backtest。股池、分数聚合、TopN 和策略参数属于 Portfolio；每份明文身份对应一个独立账户。Backtest 通过上游组合解析 ETL，或显式接收 `market_file`、`calendar_file` 和可选 `labels_file`。`portfolio_ids` 可选择部分组合；`as_of_date` 控制估值截止日。买卖费率默认 0.0005/0.0015，年化天数 252，无风险年收益率 0.012。

## 成交与估值

信号按分数降序、代码升序排名，选股不使用未来标签。引擎先更新已有持仓估值，尝试卖出到期持仓，再用可用现金买入当日目标。目标无法成交时不补入低分股票；已有同股票持仓、持仓容量和可用资金都会约束买入。

无法卖出时保留持仓和资金占用。确认停牌沿用上一可靠复权估值，后续有行情时更新估值并再次尝试退出。已持有或选中的股票缺少可靠数据时，返回 `evaluation_status=incomplete_market_data`，仍可检查暂定结果。评价截止时不强制清仓。

`missing_market_as_suspension=true` 临时将缺少行情行和显式 `missing_data` 按停牌处理：沿用上一估值、禁止成交，不因这些缺口将回测标记为不完整。该假设记录在任务输入中，不改写市场产物或标签；共享默认值为 `false`。TODO：接入独立停复牌数据，区分真实停牌与行情缺失。

同一时点价格是成交代理，不保证在完整 bar 或收盘行情形成后计算出的信号能够按该价格成交，也不模拟排队和部分成交。应先阅读产物中的执行协议，再解释策略可交易性。

```text
Equity = cash + pending event receivables + marked position value
Daily net return = equity / previous equity - 1
Daily cost = (executed buy/sell costs + event costs) / previous equity
Daily gross return = daily net return + daily cost
Turnover = (executed buy/sell notional + cash-event notional) / previous equity
```

持仓使用复权价格单位处理公司行为引起的价格变化，退出时不重复确认已经体现在估值中的收益。初始买入和后续实际成交均收费。

插件可以提供 `events` 处理器：每个 Top N 重置，在交易前处理持仓，提供当步的 `pending_cash`、`transaction_cost`、`executed_notional`。净应收款计入净值，到释放后才可买入；事件费用计入日度费用和毛收益，事件金额计入换手。账本按证券保存原始持仓记录列表，转换合并时保留每笔成本、买入日期和退出日期；非空 `tradable_at` 表示锁定，由处理器在可交易时解除。换入持仓尚未取得首个可交易报价时，复权 `units` 保留空值，避免将实物股数与复权单位相加。持仓产物按证券汇总，已完成交易保留原始记录的日期和成本。具体条款及审计由插件负责。

## 输出

| 产物        | 含义                                             |
| ----------- | ------------------------------------------------ |
| `daily`     | 按交易日历排列的收益、权益、现金、持仓及信号诊断 |
| `summary`   | 总体、年度、季度和月度统计                       |
| `orders`    | 实际成交与未成交原因                             |
| `positions` | 每日实际持仓、复权单位、权重和市值               |
| `trades`    | 已完成持有期的实际买卖价格、收益和费用           |

`daily` 使用 `topN_*` 列，`dimensions` 声明组合规模和基准。`top30_holdings` 是信号目标列表，不是实际持仓；真实敞口见 `positions`。尚未退出的持仓仍保留在该产物中，即使没有已完成交易。

## 信号诊断与基准

![Studio 0.3.0 net-return chart and Top 30 signal targets](../../figures/studio/backtest-net-return.png)

[查看高清原图](../../figures/studio/backtest-net-return.png)

**净收益** 标签页集中展示日期窗口、收益曲线与信号目标表。完整截图使用同一组合成回测。

IC、RankIC、NDCG 与目标选股共用信号当天可买候选池，包括插件选择的股池限制。IC 和 RankIC 对比预测分数与有效的固定次一市场日原始收益。NDCG 对比高分信号和相同可用收益样本的排序质量；缺标签不会补入低分候选。这些指标属于信号日期，持仓收益和估值属于组合日历日期。

`benchmark_universe_return` 是可用信号横截面的平均收益。`index_weight_*` 只有覆盖率达标时才生成加权收益代理，它们不是官方全收益指数。基准收益按标签目标日期排列，与组合估值周期对齐。

Studio 按 `portfolio_id` 的每个顶层 key 展示一个下拉框，例如 `universe`、`strategy` 和 `top_n`。选项按顺序联动，只选择实际存在的组合，并尽量保留其他字段的当前值；只有一个可选值的字段置灰。嵌套值的参数直接显示在对应下拉框中。Portfolio、回测和对比页共用此选择器。

Studio 读取选中 `portfolios[index]` 的报告，通过根级产物表解析 daily 和 summary 引用。净收益图复合每日净收益，累计毛收益图相加每日毛收益，因此后者不必等于汇总表中的复合毛收益。期间统计由任务生成，移动图表日期范围不会自动重新回测。

Studio 根据 `dimensions.top_ns` 生成收益和 NDCG 曲线，将行情不完整的评价标为暂定结果，并展示全部组合产物。预测统计只描述信号时分数和选股资格；预测输出包含分数和信号时资格，不包含未来收益或有效收益覆盖率。统计为空或标签缺失时显示不可用。

Studio 比较页保留任务元数据中的 `signals_format`，并读取展示副本中实际可用的产物。股票回测声明 `signals_format: stock-signals-v3`，通过产物引用注册日频和汇总表。基准信息比率表头使用 `dimensions.benchmarks` 声明的名称。

`net_relative_max_drawdown_<基准>` 与净 IR 共用每日超额收益（策略净收益减去同日基准收益），先按 `∏(1 + 超额收益)` 复合为净值，再计算相对历史峰值的最大回撤。初始净值 1 参与峰值计算，回撤以非正小数表示；总体、年、季、月分别重置。仅使用双方均有限的日期，无有效观察值时为空。Studio 按报告声明的平均与指数基准展示；不可用的数值显示 `—`。
