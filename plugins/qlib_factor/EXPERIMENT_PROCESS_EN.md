# Qlib Factor execution and checks

Executed on machine 45 on 2026-10-09. Training: `[20150101,20230101)`. OOS prediction/backtesting: `20230103–20261008`, 909 market dates. Rank labels, AxonX LightGBM parameters, seed 42 and 8 threads. Fees: 0.05% buy / 0.15% sell; 252-day annualization, 1.2% risk-free rate and no forced final liquidation.

Completed: factor ETL, 175-column value equality, 16 train/predict/backtest chains, training-validation selection, 12 policy backtests on two prediction sources, full prediction parity and per-order fee verification.

See [results](EXPERIMENT_RESULTS.md) for metrics and actual task identifiers. Complete metadata, logs, models and daily artifacts remain in the remote Task workspace.
