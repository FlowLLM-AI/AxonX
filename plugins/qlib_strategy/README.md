# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` inherits `qlib_factor` and `qlib_a158` to study portfolio policies using fixed predictions. The shared framework owns quotes, price limits, valuation, cash, side fees, orders, positions and trades.

## Rank-retention policy

- Retain holdings inside the current eligible TopN.
- After `minimum_holding_days` elapsed market dates, exit the worst-ranked holdings outside the buffered rank threshold first.
- Cap fills per side per day at `max(1,floor(N × replacement_fraction))`; initial construction is exempt.
- Blocked exits retain capital. Unfilled entries are not replaced, and sells precede buys. New positions receive at most 1/N equity; retained holdings are not rebalanced.

Defaults: `minimum_holding_days=10`, `replacement_fraction=0.2`, `rank_buffer=1`. Top5/10/20/30 permit 1/2/4/6 fills per side per day; this is a count cap, not a notional turnover cap. There is no fixed-expiry parameter; `planned_exit_date` is null.

Plugin version 0.3.0 requires Python 3.12+, AxonX `>=0.3.0` and upstream research plugins `>=0.3.0`. Install the layers in dependency order. Research artifacts use protocol v1.

## Install and run

Research plugins are not published to PyPI. Clone the repository and install the AxonX 0.3.0 core (`pip install -e .` from its root); run the following commands from its root. For local Agent development, install in dependency order in the execution service's Python environment:

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
axonx plugin install -e plugins/qlib_strategy
```

New `exec` processes load current Python sources. Reinstall after dependency or entry-point changes, and restart persistent services to refresh their Task catalogs, schemas and loaded dependencies. Omit `-e` for fixed-version experiments. Deploy remotely with ordinary installation, installing upstream plugins in order on the same target service; configure `AXONX_TARGET_TOKEN` first and replace the example address below:

```bash
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_factor --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_strategy --output /tmp/axonx-wheels
# Upload each actual wheel to POST /upload, then install in the order above.
axonx plugin install '<qlib_a158 upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_factor upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_strategy upload.location>' --target http://research.example:1024 --client-timeout 600
axonx exec --task qlib_strategy_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

Reuse successful base or factor predictions. Record each Task ID and `started_at` from execution logs or `status --detail full`; continue only after successful execution. Upstream `qlib_strategy_etl`, `qlib_strategy_analysis`, `qlib_strategy_train` and `qlib_strategy_predict` register factor-layer implementations; policy comparisons reuse predictions. Installation modifies the selected interpreter. New CLI processes discover installed plugins; definition Jobs and Studio retain the service startup catalog until restart. Stop on installation or verification failures.

After each installation, discard its staged upload using the returned workspace-relative `path`. Remote source paths refer to the target machine. Restart the persistent service after all layers are installed and verify definitions; see the complete [upload, verification and cleanup workflow](../../docs/en/plugins/management.md#deploy-remotely).

## Execution and configuration

`exec` runs synchronously in a fresh local CLI process. `--target` forwards it to a CLI subprocess on that service; commands return the Task exit code. Execution settings resolve as CLI options → service `get_config` → built-in defaults. Use `--workspace-dir /absolute/path` consistently for market data and upstream Tasks. Definition and status Jobs require a running service. Same-name reruns replace outputs; record both Task ID and `started_at`. Display replicas cannot be research inputs.

This layer contributes Task registrations only and has no separate application preset. Use the standard `axonx app` configuration or `--config qlib_factor`. Strategy inputs belong to `qlib_strategy_backtest`; the upstream registrations reuse factor/base implementations. Prediction accepts a Train and an optional compatible ETL to score new data.

## Local validation

From the repository root, with all three research plugins and development dependencies installed:

```bash
python -m pytest plugins/qlib_strategy/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

The research tests execute the factor and strategy chains against temporary synthetic market data, including artifact exchange and explicit prediction ETL selection.

## Experiments

Settings, full results and artifact provenance are maintained in the [research experiment guide](../../docs/en/research/alpha158-case.md). The three configurations were rerun on machine 45 with 0.05% buy / 0.15% sell fees.

AxonX owns protocol v1 in `axonx.task.models.artifacts`, with `TaskType` as `task_type` and task-relative artifact records (`path`, `size`, `revision`). Revisions use `size:mtime_ns`; they are file versions, not content checksums. Training publishes `output_params.protocol` and a `models.json` collection. Prediction snapshots model members and pins upstream artifacts through `axonx.task.storage.inputs`. Feature semantics and fingerprints belong to `axonx_qlib_a158.internal.protocol`; training, analysis and prediction validate this contract before consuming data. Prediction publishes `model_identity`, `dates`, `score_columns` and its file revision. Consumers require protocol headers and matching feature semantics.

Backtests publish **all market** (`all`) and **CSI 300** (`hs300`) as independent reports in one Task. Studio provides a universe dropdown, including independent selections in strategy comparison. Positive signal-time `index_weight_hs300` defines CSI 300 membership. The backtest schema uses `default_universe`, `universes` and a shared artifact registry.
