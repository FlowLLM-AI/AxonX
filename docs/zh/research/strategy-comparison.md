---
title: 策略比较
description: 在共同日期、相同组合规模和明确口径下比较两个回测结果。
---

# 策略比较

Studio 策略比较页面读取两个 Backtest Task 的日频产物，在共同有效日期上重新计算收益与风险。比较不提交新的研究任务，也不会修改原有产物。

本页解释比较界面的计算与操作。比较方案的控制变量、筛选规则和独立确认窗口应事先按[实验设计与确认](experiments.md)定义。

![共同窗口比较](../../figures/research/comparison-window.svg)

## 准备两组实验

用不同任务名称保留不同训练、预测和回测结果。比较同一因素的变化时，其他设置尽量一致，例如使用同一 ETL、同一预测窗口，仅调整训练参数或成本。

```bash
axonx submit --task qlib_a158_backtest --task-name fixed-holding \
  --source-tasks '<Predict Task ID>' --top-ns '[20,30]' --holding-days 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
axonx submit --task qlib_strategy_backtest --task-name rank-retention \
  --source-tasks '<Predict Task ID>' --top-ns '[20,30]' --minimum-holding-days 3 \
  --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015
```

各自等待成功后，在策略比较页面选择 A 和 B。Task ID 是实验身份，显示名称只能帮助识别；固定名称重跑替换目录后，无法把原结果当成仍保留的历史实验。

## 页面操作顺序

![Strategy comparison overview](../../figures/studio/strategy-overview.png)

截图来自远程工作区已有的两个实验。**Prediction sources differ** 提醒上游预测不同，应结合血缘解释差异；页面数值不是本文参数示例的预期收益。

1. 选择当前机器以及两条成功回测记录。
2. 核对输入参数差异与页面警告。页面会提示行情不完整和记账协议版本不同。
3. 选择双方都支持的 Top N。
4. 设定共同日期区间，核对观察天数。
5. 先看净收益与回撤，再看信号质量、分期收益和目标清单交集。

没有共同组合规模或共同有效日时，页面无法建立可比较样本。不要用各自总窗口的指标替代共同窗口结果。

## 共同窗口如何建立

`pairDays` 按 `trade_date` 配对，只有双方对应 `topN_net_return` 都为有限值的日期才保留，再按日期排序。用户选择的起止日期进一步过滤这个配对集合。

```text
A 日期：01、02、03、04
B 日期：    02、03、04、05
双方有效净收益日期：02、03、04
选择 03 至 05 后：03、04
```

这只是日期和值的对齐，不会自动证明两策略训练窗口、股票池、交易成本或成交假设相同。缺失日期被删除后，累计收益沿剩余日期重新连接，不应理解为原完整净值轨迹。

## 指标由谁计算

| 展示内容                             | 数据来源与计算位置               |
| ------------------------------------ | -------------------------------- |
| 原回测汇总表                         | 插件生成 `summary.parquet`       |
| 比较页净收益、年化、波动、回撤、胜率 | 前端在共同可见窗口重算           |
| 比较页平均换手                       | 共同窗口中有限换手值的平均       |
| 比较页分年/季/月收益                 | 前端分组并重算净累计收益         |
| IC / RankIC 对比                     | 共同日期中双方指标都有限的子样本 |
| 目标重合                             | 当日 `top30_holdings` 中代码集合 |

即使两个任务本来包含相同日期，用户缩短窗口后也会改变年化、波动和回撤。插件汇总与比较页可能数值不同，先核对观察范围及年化设置。

## 收益与风险口径

![Strategy return and risk comparison](../../figures/studio/strategy-return-risk.png)

在 **Return & risk** 切换 Net 与 Gross。图内缩放条可以只观察末段走势；图表局部缩放与页面起止日期筛选是两种操作，解释指标时仍核对页面共同窗口。

净累计收益按日净收益复利；毛收益曲线按日毛收益累加。年化波动使用样本标准差，最大回撤包含初始净值 1，胜率只把净收益大于零计为获胜。

比较页读取任务输入的 `annualization_days`：双方有限且相同时采用该值；不一致或缺失时回退 252。不一致时会展示年化差异提示。分期收益只重算累计净收益，不需要年化参数。

若共同窗口不足两个观测，样本标准差、波动和比率等可能无法给出有限值，页面以缺失值展示。不能用单日结果评估稳定性。

## 信号质量与目标差异

![Strategy signal quality comparison](../../figures/studio/strategy-quality.png)

**Signal quality** 可选择 IC 或 RankIC 趋势，图中为 RankIC 的 MA20。空值与有效观测数仍按下面的配对规则处理。

`pairedMean` 和 `pairedRatio` 会再次要求双方 IC 或 RankIC 都有限，因此信号质量的有效天数可能少于净收益共同窗口。20 行滚动质量曲线分别过滤各侧有效值，应连同有效样本与空值阅读。

目标重合率使用 Jaccard 定义：

```text
重合率 = 两边目标代码交集数量 / 两边目标代码并集数量
A = {a, b, c}，B = {b, c, d}：交集 2 / 并集 4 = 50%
```

它不是交集除以 30，也不是资金加权重合。当前页面读取 `top30_holdings`，切换收益 Top N 不会变成相应规模的真实仓位比较。对 qlib_a158，它比较的是 Top 30 信号目标，包含未成交候选。

## 分期收益与交易观察

![Strategy period comparison](../../figures/studio/strategy-periods.png)

**Periods** 按 Year、Quarter 或 Month 查看共同窗口内的分期净收益及 B−A 差值。同一策略可以在不同年份表现不同，分期结果帮助定位总体差异来自哪一段。

![Strategy trading comparison](../../figures/studio/strategy-trading.png)

**Trading & holdings** 先展示平均换手、日均成本与换手走势。继续观察目标交集时，沿用上一节对 Top 30 字段的限制，不能把高目标重合当作真实资金仓位重合。

## 如何形成可靠结论

记录两条 Task ID、共同窗口、Top N、成本、年化设置和执行协议。确认结果变化来自预期因素，再用血缘检查上游数据是否相同。

收益差异可以来自评分、候选池、权重覆盖、资金被延期仓位占用或成本。先解释这些机制，再讨论模型改善。页面警告用于暴露已知设置差异，不是研究可比性的自动认证。

## 常见问题

| 现象                         | 判断方向                            |
| ---------------------------- | ----------------------------------- |
| 比较页收益与单任务页面不一致 | 两页窗口、共同有效日、复利/累加口径 |
| IC 有效天数更少              | 双方 IC 有限值交集                  |
| 切换 Top N 后目标表相似      | 目标表始终是 Top 30 字段            |
| 重合率不是共同股票数除以 30  | 使用交集/并集                       |
| 风险指标为空                 | 观察数量、非有限值或零方差          |

## 相关文档与实现

- [回测结果解读](backtest.md)、[任务血缘](../concepts/task-lineage.md)
- [`比较数据模型`](../../../axonx_studio/src/features/research/compare/model.ts)
- [`比较页面与参数警告`](../../../axonx_studio/src/features/research/compare/StrategyComparePage.tsx)

Studio 比较实际生效的买卖费率，并在共同交易窗口展示产物记录的平均成交费用，支持分侧费率与显式零费率。
