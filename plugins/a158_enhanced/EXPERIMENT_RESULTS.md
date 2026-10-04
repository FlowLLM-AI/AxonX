# 横截面环境增强版实验结果

执行目标：用户指定的远程 AxonX 服务（地址仅保存在本地配置）。增强ETL：`etl#a158e_etl#202610021764NJ`。原始字段逐值一致性检查已通过。

## 筛选期：2023–2024

| 方案 | RankIC | Top10净年化 | Top20净年化 | Top10净Sharpe | Top20净Sharpe | Top10回撤 | Top20回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.0876 | -26.11% | -17.59% | -0.8294 | -0.6058 | -51.80% | -47.67% |
| market | 0.0915 | -4.60% | -10.23% | -0.0561 | -0.3111 | -39.29% | -43.30% |
| relative | 0.0939 | 5.34% | -4.40% | 0.2824 | -0.0737 | -33.83% | -38.33% |
| all | 0.0974 | 18.38% | 12.05% | 0.6694 | 0.4972 | -34.65% | -34.91% |

锁定方案：`all`（`market,liquidity,relative,interaction`）。三项主指标筛选门槛：通过。

## 最终确认期：2025-01-01至2026-09-30

| 方案 | RankIC | Top10净年化 | Top20净年化 | Top10净Sharpe | Top20净Sharpe | Top10回撤 | Top20回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0.0915 | -5.74% | -3.24% | -0.0631 | -0.0058 | -39.48% | -38.43% |
| all | 0.0967 | 28.21% | 24.93% | 0.9430 | 0.9040 | -31.53% | -31.08% |

最终确认结论：RankIC、Top10和Top20净年化收益均提升。
差值：RankIC +0.0052；Top10净年化 +33.95%；Top20净年化 +28.16%（收益差为百分点）。
需要同时看到：确认期Top1–3收益下降，且三项日配对增量的95%区块bootstrap区间均跨零。模型gain排名也不等同于单个特征的独立贡献。

## 分年表现

| 阶段 | 方案 | 年份 | RankIC | Top10净年化 | Top20净年化 | Top10回撤 | Top20回撤 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| selection | baseline | 2023 | 0.0891 | -15.61% | -13.58% | -27.81% | -23.50% |
| selection | baseline | 2024 | 0.0862 | -35.66% | -21.19% | -40.99% | -33.69% |
| selection | market | 2023 | 0.0938 | 7.00% | 3.55% | -18.54% | -18.33% |
| selection | market | 2024 | 0.0891 | -15.37% | -23.15% | -28.59% | -33.41% |
| selection | relative | 2023 | 0.0967 | 11.84% | 0.38% | -15.59% | -19.09% |
| selection | relative | 2024 | 0.0911 | -1.73% | -10.15% | -32.96% | -33.04% |
| selection | all | 2023 | 0.0983 | 3.94% | 9.07% | -25.86% | -18.61% |
| selection | all | 2024 | 0.0965 | 31.38% | 12.62% | -22.76% | -29.35% |
| confirmation | baseline | 2025 | 0.1013 | 10.47% | 11.99% | -21.85% | -15.75% |
| confirmation | baseline | 2026 | 0.0783 | -23.83% | -20.47% | -39.48% | -38.43% |
| confirmation | all | 2025 | 0.1086 | 34.08% | 38.86% | -16.50% | -13.37% |
| confirmation | all | 2026 | 0.0808 | 20.72% | 8.40% | -31.53% | -31.08% |

## 最终确认期全部TopN

| TopN | 基线净年化 | 增强净年化 | 基线最大回撤 | 增强最大回撤 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 68.32% | -18.07% | -64.43% | -69.36% |
| 2 | 78.74% | 11.95% | -45.54% | -41.86% |
| 3 | 38.22% | 15.61% | -46.90% | -35.39% |
| 5 | 11.34% | 15.19% | -40.92% | -36.63% |
| 10 | -5.74% | 28.21% | -39.48% | -31.53% |
| 15 | 1.58% | 24.23% | -38.27% | -31.70% |
| 20 | -3.24% | 24.93% | -38.43% | -31.08% |
| 30 | 2.13% | 19.10% | -38.21% | -30.44% |

## 市场环境诊断

按信号日市场等权收益划分：低于−1%、高于+1%、其余。表格只比较信号日RankIC/NDCG，避免将延迟持仓的退出日净收益误归到信号日环境。

| 阶段 | 方案 | 环境 | 天数 | RankIC | Top10 NDCG | Top20 NDCG |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| confirmation | all | market_down_gt1pct | 76 | 0.0955 | 0.5068 | 0.5013 |
| confirmation | all | market_middle | 245 | 0.0923 | 0.4820 | 0.4822 |
| confirmation | all | market_up_gt1pct | 102 | 0.1084 | 0.4901 | 0.4912 |
| confirmation | baseline | market_down_gt1pct | 76 | 0.0848 | 0.4981 | 0.4997 |
| confirmation | baseline | market_middle | 245 | 0.0899 | 0.4667 | 0.4663 |
| confirmation | baseline | market_up_gt1pct | 102 | 0.1002 | 0.4977 | 0.4953 |
| selection | all | market_down_gt1pct | 90 | 0.0672 | 0.4690 | 0.4714 |
| selection | all | market_middle | 291 | 0.0987 | 0.4997 | 0.4961 |
| selection | all | market_up_gt1pct | 103 | 0.1202 | 0.5102 | 0.5116 |
| selection | baseline | market_down_gt1pct | 90 | 0.0734 | 0.4839 | 0.4870 |
| selection | baseline | market_middle | 291 | 0.0944 | 0.4750 | 0.4767 |
| selection | baseline | market_up_gt1pct | 103 | 0.0810 | 0.4641 | 0.4655 |
| selection | market | market_down_gt1pct | 90 | 0.0639 | 0.4812 | 0.4789 |
| selection | market | market_middle | 291 | 0.0980 | 0.4945 | 0.4919 |
| selection | market | market_up_gt1pct | 103 | 0.0969 | 0.4710 | 0.4698 |
| selection | relative | market_down_gt1pct | 90 | 0.0688 | 0.4855 | 0.4767 |
| selection | relative | market_middle | 291 | 0.0975 | 0.4930 | 0.4900 |
| selection | relative | market_up_gt1pct | 103 | 0.1056 | 0.4857 | 0.4894 |

## 日配对差异

同日增强减基线，使用20交易日循环区块bootstrap（2000次、seed=42）给出均值差区间。该区间不代表年化复利收益差。

| 阶段 | 指标 | 天数 | 日均差 | 95%区间 |
| --- | --- | ---: | ---: | --- |
| selection | rank_ic | 484 | +0.009765 | [+0.000186, +0.020695] |
| selection | top10_net_return | 485 | +0.001849 | [+0.000441, +0.003345] |
| selection | top20_net_return | 485 | +0.001231 | [+0.000423, +0.002135] |
| confirmation | rank_ic | 423 | +0.005233 | [-0.001210, +0.010815] |
| confirmation | top10_net_return | 424 | +0.001195 | [-0.000435, +0.002956] |
| confirmation | top20_net_return | 424 | +0.000993 | [-0.000256, +0.002348] |

## 选定模型中的环境特征

以下按树模型gain排序，属于模型使用程度诊断，不是每个特征独立提升效果的证明。

| 特征 | Gain | Split次数 |
| --- | ---: | ---: |
| `f_context_return_rank` | 10836.0097 | 280 |
| `f_context_relative_trend5` | 8088.9877 | 122 |
| `f_context_market_trend20` | 7577.7071 | 549 |
| `f_context_limit_up_ratio` | 7160.4376 | 486 |
| `f_context_group_relative_return` | 6848.3173 | 73 |
| `f_context_return_iqr` | 6814.3952 | 518 |
| `f_context_amount_concentration` | 6697.7094 | 511 |
| `f_context_amount_rank20` | 6138.1786 | 233 |
| `f_context_market_amount_ratio` | 5941.9832 | 449 |
| `f_context_market_trend5` | 5482.5632 | 397 |

## 复现与限制

- 所有方案使用相同训练区间、标签尾部过滤、随机种子42和原始交易费用0.002；没有根据最终确认期继续调参。
- 净Sharpe使用扣费后日收益减日无风险收益计算；原始回测中的gross Sharpe不作为净Sharpe。
- 回测继承原插件的收盘成交代理、延迟退出和未结清持仓按成本记账规则；结果是历史研究口径，未模拟盘后排队、部分成交或逐日未实现盈亏。
- 首次复制误改原特征名称的运行已归档于 `experiments/superseded_feature_namespace/`，对应增强训练已取消，不参与结果。
- 精确句柄和完整结果保存在本地 `experiments/*_submit.json`、`*_status.json`、`*_summary.csv`、`*_daily.parquet`，不随仓库提交。可阅读指标与校验汇总见 [材料索引](experiments/README.md)。
