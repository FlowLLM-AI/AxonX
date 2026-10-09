# Qlib Factor 实验结果

[English](EXPERIMENT_RESULTS.md) · [简体中文](EXPERIMENT_RESULTS_ZH.md)

2026-10-09 在 45 机器执行。训练 `[20150101,20230101)`，样本外预测与回测 `20230103–20261008`，909 个市场日。标签 rank、AxonX LightGBM 参数、种子 42、8 线程；买入 0.05% / 卖出 0.15%，252 日年化、无风险利率 1.2%，不强制期末平仓。

按训练期内部验证 RankIC 选择 `liquidity`，共 164 个模型特征。训练 5,838,557 行；选组不使用 2023 年后的收益。

## 全部因子组合

| Groups                                | Features | Rounds | Validation RankIC | OOS RankIC | Top5   | Top10  | Top20  | Top30  |
| ------------------------------------- | -------- | ------ | ----------------- | ---------- | ------ | ------ | ------ | ------ |
| liquidity                             | 164      | 288    | 0.1132            | 0.0976     | 8.86%  | -5.33% | -1.83% | -1.58% |
| liquidity,relative                    | 169      | 277    | 0.1118            | 0.0983     | 1.46%  | 5.40%  | -0.72% | -2.92% |
| market,liquidity                      | 175      | 338    | 0.1115            | 0.0985     | 15.13% | 12.49% | 3.27%  | 0.65%  |
| market,liquidity,relative,interaction | 184      | 415    | 0.1112            | 0.0980     | 14.07% | 13.62% | 7.21%  | 4.32%  |
| liquidity,interaction                 | 168      | 273    | 0.1110            | 0.0988     | 14.79% | 17.00% | 8.15%  | 7.83%  |
| market,liquidity,relative             | 180      | 322    | 0.1107            | 0.0984     | 7.98%  | 7.20%  | 6.52%  | 4.26%  |
| liquidity,relative,interaction        | 173      | 280    | 0.1107            | 0.0990     | 11.03% | 3.85%  | 5.26%  | 1.82%  |
| market                                | 169      | 352    | 0.1105            | 0.0954     | 12.12% | 6.23%  | 2.50%  | -1.15% |
| relative                              | 163      | 375    | 0.1100            | 0.0961     | 19.40% | 7.31%  | 0.32%  | -3.43% |
| market,liquidity,interaction          | 179      | 319    | 0.1098            | 0.0997     | 27.32% | 20.44% | 12.19% | 6.99%  |
| relative,interaction                  | 167      | 370    | 0.1094            | 0.0970     | 18.36% | 17.62% | 7.09%  | 1.77%  |
| market,relative,interaction           | 178      | 419    | 0.1089            | 0.0970     | 8.53%  | 5.07%  | 1.25%  | -1.42% |
| market,relative                       | 174      | 285    | 0.1088            | 0.0955     | 11.63% | 0.56%  | -1.70% | -4.44% |
| market,interaction                    | 173      | 415    | 0.1081            | 0.0981     | 12.69% | 10.31% | 2.04%  | -0.32% |
| none                                  | 158      | 422    | 0.1079            | 0.0923     | 23.42% | 14.00% | 7.67%  | 0.97%  |
| interaction                           | 162      | 393    | 0.1079            | 0.0972     | 10.91% | 11.56% | 7.67%  | 6.85%  |

TopN 列为扣费年化收益。完整风险、换手及 Task / Run ID 见 [factor_comparison.csv](experiments/factor_comparison.csv)，分年结果见 [yearly_comparison.csv](experiments/yearly_comparison.csv)。

本轮 `liquidity` 的样本外 RankIC 为 0.0976，高于基础层的 0.0923，但普通回测四个 TopN 的净年化均低于基础层。默认组依据训练内验证选择，本轮结果完整保留这一差异。

## 锁定增强方案

| TopN | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Turnover | Daily cost |
| ---- | -------------- | -------------- | ------------ | ---------- | -------- | ---------- |
| 5    | 8.86%          | 35.84%         | -37.24%      | 0.3929     | 199.10%  | 0.20%      |
| 10   | -5.33%         | -17.93%        | -40.26%      | -0.0805    | 199.25%  | 0.20%      |
| 20   | -1.83%         | -6.46%         | -35.35%      | 0.0368     | 199.20%  | 0.20%      |
| 30   | -1.58%         | -5.57%         | -34.34%      | 0.0409     | 199.18%  | 0.20%      |

模型特征重要性见 [selected_feature_importance.csv](experiments/selected_feature_importance.csv)。

## 数据与执行核对

ETL 11,446,950 行，184 个特征；基础层 175 个共同字段逐值一致，26 个新增特征覆盖率见 [coverage](experiments/context_feature_coverage.csv)。行情文件序列化摘要可不同，实际行情、标签及日历逐值一致；全部回测显式复用基础层的三个产物，输入 SHA-256 一致。none 对照的完整预测与基础层逐值一致。

所有实际成交订单的分侧收费已逐条核对；未成交订单收费为零。部分订单缺行情，回测为 `incomplete_market_data`；缺报价沿用旧估值，无法退出继续占用资金。

## 任务来源

| Variant / stage                                | Task ID                                      | Run ID                           |
| ---------------------------------------------- | -------------------------------------------- | -------------------------------- |
| etl                                            | etl#qlib_factor_etl#2026100913ikIF           | 3bab4229a2014ec885748865003189e0 |
| liquidity train                                | train#qlib_factor_train#2026100913CHT3       | a9ae1f4a95034aed891b05a13147752a |
| liquidity predict                              | predict#qlib_factor_predict#2026100913xIIV   | 2dea2780aa2f4277a8c70a4353d0f168 |
| liquidity backtest                             | backtest#qlib_factor_backtest#2026100913b7vt | d2cd9458ea6c491f86636fa325aa338b |
| liquidity,relative train                       | train#qlib_factor_train#2026100913SDGk       | 314a55c4c24c44f0bf84ffdf35763580 |
| liquidity,relative predict                     | predict#qlib_factor_predict#2026100914Hy10   | 378ad6ca266a4e62aaf819cc3c78111d |
| liquidity,relative backtest                    | backtest#qlib_factor_backtest#2026100914HGdE | 975e7b531f484b76acbb0c7f0c03e3b8 |
| market,liquidity train                         | train#qlib_factor_train#2026100913idaD       | 9f07e381c5c24831a7b2f59006759e4f |
| market,liquidity predict                       | predict#qlib_factor_predict#2026100913c54l   | e42c15569f5e45089a62a5868ec9d071 |
| market,liquidity backtest                      | backtest#qlib_factor_backtest#20261009138CEa | b7663fafd1fd437692b070483722452b |
| market,liquidity,relative,interaction train    | train#qlib_factor_train#2026100913AZkV       | b23373e24f0342028ac3b90b552272bb |
| market,liquidity,relative,interaction predict  | predict#qlib_factor_predict#2026100914LivI   | ce6de6b4cb1c4e2a9af239ce8e04fe94 |
| market,liquidity,relative,interaction backtest | backtest#qlib_factor_backtest#2026100914uf3U | 04fc5bf3a08648afb2fedb67e1432f39 |
| liquidity,interaction train                    | train#qlib_factor_train#2026100913tkj2       | e0e7dfcdd5214677831516bf53d86b89 |
| liquidity,interaction predict                  | predict#qlib_factor_predict#2026100914cvwN   | 0c3b91113cd54267af1e51348709d76f |
| liquidity,interaction backtest                 | backtest#qlib_factor_backtest#2026100914pm75 | 15d3da0fb86b48e9b511985cb3254d56 |
| market,liquidity,relative train                | train#qlib_factor_train#2026100913Znz9       | c40fcb3a36c042ca81c24216b34a27dd |
| market,liquidity,relative predict              | predict#qlib_factor_predict#2026100914YhiG   | f25e4d20e3e543c5aa33a4d7efdfa2ff |
| market,liquidity,relative backtest             | backtest#qlib_factor_backtest#2026100914po9d | 06cf2515de634f11afe8bfbf86c6bf9f |
| liquidity,relative,interaction train           | train#qlib_factor_train#2026100913HdoY       | 7724bd5ec75744a8a7318edb46c13021 |
| liquidity,relative,interaction predict         | predict#qlib_factor_predict#2026100914XIAb   | d9706d84080248fb97dcac8df4bb1a98 |
| liquidity,relative,interaction backtest        | backtest#qlib_factor_backtest#2026100914hgeG | a84338de289d456e87fb03fa85b19023 |
| market train                                   | train#qlib_factor_train#2026100913F60j       | bbac6342a0d5444489dfa8a225b4ac94 |
| market predict                                 | predict#qlib_factor_predict#2026100913lGdx   | 6b6a5fbcd56041aeb8cd687b28303054 |
| market backtest                                | backtest#qlib_factor_backtest#2026100913phrU | 4af1c26d7a1a4a2db0033444b207af92 |
| relative train                                 | train#qlib_factor_train#2026100913oswX       | 538a8550eabe43afbd3836d8d7f4a3b3 |
| relative predict                               | predict#qlib_factor_predict#2026100913dVkv   | 788c6cde556442b0a3eed4f167435da1 |
| relative backtest                              | backtest#qlib_factor_backtest#2026100913DxB0 | 511e684c385b48ddba3dde5e1a241e13 |
| market,liquidity,interaction train             | train#qlib_factor_train#2026100913MKKc       | 45bf4fdf63964d88a160ff4c7642c746 |
| market,liquidity,interaction predict           | predict#qlib_factor_predict#202610091411tG   | 7ae31d690c4440609148ddbd847593f4 |
| market,liquidity,interaction backtest          | backtest#qlib_factor_backtest#20261009145Mhv | b5da5e08e9914f8082017740af17b025 |
| relative,interaction train                     | train#qlib_factor_train#20261009136ls3       | 85089445252e4cae87dcdce4dbf349cd |
| relative,interaction predict                   | predict#qlib_factor_predict#2026100914yxXQ   | 2605dfd550a149c79d2ef010850a4cdc |
| relative,interaction backtest                  | backtest#qlib_factor_backtest#2026100914IT9E | a67c2be84b324b26a65c800581a56e09 |
| market,relative,interaction train              | train#qlib_factor_train#2026100913nRQp       | 26af4fa9076e44e6b7a32a4d131aa45c |
| market,relative,interaction predict            | predict#qlib_factor_predict#2026100914qzC6   | 75ea16bf7aad4c1e99ebe1c72da8f4d6 |
| market,relative,interaction backtest           | backtest#qlib_factor_backtest#2026100914Avoy | 1a47840e1c644476a50961792d47b69d |
| market,relative train                          | train#qlib_factor_train#2026100913LY7E       | c011b172f41f4b0d8c511688c001e863 |
| market,relative predict                        | predict#qlib_factor_predict#2026100913v2kc   | cdcb1e31cb314eb7b5cb14cc619c104b |
| market,relative backtest                       | backtest#qlib_factor_backtest#2026100913Zksr | fc23a24e70b543a79b7ec09bd0b063ca |
| market,interaction train                       | train#qlib_factor_train#20261009132C5E       | b5eeeb5fe4b148b38caefe794dec26d8 |
| market,interaction predict                     | predict#qlib_factor_predict#2026100913xOYk   | 462b99fc86aa4f58840484fbb1e5c712 |
| market,interaction backtest                    | backtest#qlib_factor_backtest#2026100913oP0M | a8823571a49e4148a4356e118a4ee6f4 |
| none train                                     | train#qlib_factor_train#2026100913zYpB       | 26033c26768e4f289b630d2df81cd653 |
| none predict                                   | predict#qlib_factor_predict#2026100913oUF7   | 45e52705aec84efdbb8b3e7e56dccc2c |
| none backtest                                  | backtest#qlib_factor_backtest#2026100913F5ew | d02d71d35d564a3faddf0e6591b8ecb6 |
| interaction train                              | train#qlib_factor_train#2026100913NKHI       | 6ca3d5abd26c48ec8aa75402e8e56890 |
| interaction predict                            | predict#qlib_factor_predict#2026100913uogL   | 78ac9f5dfa6249a19a044f53cfc2ec08 |
| interaction backtest                           | backtest#qlib_factor_backtest#2026100913Buz5 | d55368cc1606401ca8e3525f44bbf814 |

完整输入、模型、逐日产物与日志保存在对应远程任务中。其他窗口的实验记录见 [归档](archives/20261009/README.md)。
