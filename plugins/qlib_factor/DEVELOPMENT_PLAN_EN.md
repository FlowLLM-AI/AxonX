# Qlib Factor experiment plan

[简体中文](DEVELOPMENT_PLAN.md)

Fix the base scheme at rank × AxonX parameters. Train on `[20150101,20230101)` and evaluate `20230103–20261008`. Keep universe, label tails, seed, threads, trading restrictions, Top5/10/20/30 and fees identical: 0.05% buy / 0.15% sell.

Test all 15 nonempty combinations of market/liquidity/relative/interaction plus a none control. Compare shared base features and state columns value by value, along with market, labels and calendar. All backtests explicitly reuse the same base market artifacts.

Select the nonempty context group with highest training-period validation RankIC; ties prefer fewer features, then group name. Refit the full training period and report OOS signals and net returns from 2023. Fix the primary policy in advance at 10 days, a 20% daily count cap and rank_buffer=1; compare six holding periods on both prediction sources.

Raw daily artifacts, complete metadata, logs and models remain in remote tasks. The repository contains documentation, key settings, aggregate metrics and task provenance.
