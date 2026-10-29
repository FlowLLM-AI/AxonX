# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` extends `qlib_a158` to study portfolio policies using fixed predictions. The shared framework owns quotes, price limits, valuation, cash, side fees, orders, positions and trades.

## Rank-retention policy

- Retain holdings inside the current eligible TopN.
- After `minimum_holding_days` elapsed market dates, exit the worst-ranked holdings outside the buffered rank threshold first.
- Cap fills per side per day at `max(1,floor(N × replacement_fraction))`; initial construction is exempt.
- Blocked exits retain capital. Unfilled entries are not replaced, and sells precede buys. New positions receive at most 1/N equity; retained holdings are not rebalanced.

Defaults: `minimum_holding_days=10`, `replacement_fraction=0.2`, `rank_buffer=1`. Top5/10/20/30 permit 1/2/4/6 fills per side per day; this is a count cap, not a notional turnover cap. `rank_buffer` must be finite. There is no fixed-expiry parameter; `planned_exit_date` is null.

Plugin version 0.3.0 requires Python 3.12+, AxonX `>=0.3.0` and upstream research plugins `>=0.3.0`. Install the layers in dependency order. Research artifacts use protocol v1.

## Install and run

Research plugins are not published to PyPI. Clone the repository and install the AxonX 0.3.0 core (`pip install -e .` from its root); run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_strategy
```

For remote installation and service refresh, follow [plugin management](../../docs/en/plugins/management.md). The examples below require installed plugins/data, `AXONX_TARGET_TOKEN`, and your service address in place of `http://research.example:1024`.

```bash
axonx exec --task qlib_strategy_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Reuse successful base or factor predictions. Record each Task ID and `started_at` from execution logs or `status --detail full`; continue only after successful execution. The plugin registers only `qlib_strategy_backtest`; policy comparisons reuse base or factor predictions. Installation modifies the selected interpreter. New CLI processes discover installed plugins; definition Jobs and Studio retain the service startup catalog until restart. Stop on installation or verification failures.

## Execution and configuration

Use the standard `axonx app` configuration. This plugin registers only `qlib_strategy_backtest` and depends on `qlib_a158`; `qlib_factor` is optional. Create predictions with the base or factor training Tasks and `qlib_a158_predict`. Prediction accepts a Train and an optional compatible ETL to score new data.

## Local validation

From the repository root, with all three research plugins and development dependencies installed:

```bash
python -m pytest plugins/qlib_strategy/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

The research tests execute the factor and strategy chains against temporary synthetic market data, including artifact exchange and explicit prediction ETL selection.

## Experiments

Shared settings, results, reproduction commands and Task provenance are maintained in the [Alpha158 improvement case](../../docs/en/research/alpha158-case.md). Artifact fields and universe reports follow the [shared protocol](../../docs/en/reference/research-artifacts.md).
