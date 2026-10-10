# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` inherits `qlib_factor` and `qlib_a158` to study portfolio policies using fixed predictions. The shared framework owns quotes, price limits, valuation, cash, side fees, orders, positions and trades.

## Rank-retention policy

- Retain holdings inside the current eligible TopN.
- After `minimum_holding_days` elapsed market dates, exit the worst-ranked holdings outside the buffered rank threshold first.
- Cap fills per side per day at `max(1,floor(N × replacement_fraction))`; initial construction is exempt.
- Blocked exits retain capital. Unfilled entries are not replaced, and sells precede buys. New positions receive at most 1/N equity; retained holdings are not rebalanced.

Defaults: `minimum_holding_days=10`, `replacement_fraction=0.2`, `rank_buffer=1`. Top5/10/20/30 permit 1/2/4/6 fills per side per day; this is a count cap, not a notional turnover cap. There is no fixed-expiry parameter; `planned_exit_date` is null.

## Install and run

Research plugins are not published to PyPI. Install the AxonX core and clone the repository; run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
axonx plugin install -e plugins/qlib_strategy
```

Restart persistent services after Python source changes; reinstall after dependency or entry-point metadata changes. Omit `-e` for fixed-version experiments. Deploy remotely with ordinary installation, installing upstream plugins in order on the same target service; configure `AXONX_TARGET_TOKEN` first and replace the example address below:

```bash
axonx plugin install plugins/qlib_a158 --target http://research.example:1024
axonx plugin install plugins/qlib_factor --target http://research.example:1024
axonx plugin install plugins/qlib_strategy --target http://research.example:1024
axonx submit --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Reuse successful base or factor predictions. Record returned Task / Run IDs and wait for success before reading results. Upstream `qlib_strategy_etl`, `qlib_strategy_analysis`, `qlib_strategy_train` and `qlib_strategy_predict` register factor-layer implementations; policy comparisons reuse predictions. Task-only wheel updates through the remote installation Job apply without restarting; restart when `restart_required` is true and verify Task definitions. Direct pip/source changes require restart. Use compatible AxonX core and plugin versions, following the plugin package requirements.

## Experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/alpha158-case.md). The three configurations were rerun on machine 45 with 0.05% buy / 0.15% sell fees.
