# Qlib Alpha158: labels and model parameters

[English](EXPERIMENT_RESULTS.md) · [简体中文](EXPERIMENT_RESULTS_ZH.md)

Four runs on machine 45 on 2026-10-09: `rank/csz × axonx/qlib`, sharing one successful ETL. Training is `[20150101, 20230101)`; prediction starts at `20230101`. Actual backtesting covers `20230103–20261008`, with 909 trading days.

## Shared settings

ETL: 11,446,950 rows, 5,477 Shanghai/Shenzhen stocks and 158 features. The recent 14-day download completed and `stock_basic` includes delisting dates. October 9 daily quotes were unavailable, so evaluation ends on October 8.

Both labels use T→T+1 adjusted returns, trimming 2.5% from each raw-return tail. Rank is computed per day; CSZ clips each tail at 2.5% and normalizes per day (`ddof=0`). Both signal and label-end dates respect the training cutoff. The last 10% of training dates select boosting rounds before refitting the full training period. Seed 42, 8 threads, maximum 1000 rounds and 50-round early stopping. Only the label and LightGBM preset vary.

Fixed one-day holding, Top5/10/20/30, exchange price limits and retained positions when exits are blocked. Same-close quote proxy, sells before buys, 0.2% per executed side as the baseline, with an additional 0.05% buy / 0.15% sell backtest, 252-day annualization, 1.2% annual risk-free rate and no forced final liquidation. The qlib preset supplies model hyperparameters; labels, training lifecycle and backtesting use the current AxonX scheme.

## Model parameters

| Parameter          | axonx |     qlib |
| ------------------ | ----: | -------: |
| `learning_rate`    |  0.03 |      0.2 |
| `num_leaves`       |    31 |      210 |
| `max_depth`        |    -1 |        8 |
| `feature_fraction` |   0.9 |   0.8879 |
| `bagging_fraction` |   0.9 |   0.8789 |
| `bagging_freq`     |     1 |        0 |
| `lambda_l1`        |   0.0 | 205.6999 |
| `lambda_l2`        |   0.0 | 580.9768 |

## Training and signals

| Combination  | Training rows | Best rounds | Validation RankIC | OOS IC | OOS RankIC |
| ------------ | ------------: | ----------: | ----------------: | -----: | ---------: |
| rank × axonx |     5,838,557 |         422 |            0.1079 | 0.0530 |     0.0923 |
| rank × qlib  |     5,838,557 |          37 |            0.1042 | 0.0501 |     0.0891 |
| csz × axonx  |     5,838,557 |         392 |            0.1007 | 0.0541 |     0.0833 |
| csz × qlib   |     5,838,557 |          23 |            0.0965 | 0.0511 |     0.0801 |

Early stopping selects rounds using validation L2 for each target. Validation RankIC is shown for signal comparison; OOS metrics use the shared backtest interval. Rank and CSZ have different target scales, so L2 is not compared across labels.

## Backtests with 0.05% buy / 0.15% sell fees

Reuse the four predictions above and set `buy_cost_rate=0.0005` and `sell_cost_rate=0.0015` (0.05% buy / 0.15% sell). Training, predictions, market, calendar, TopN, holding period and backtest interval remain identical. All input-artifact SHA-256 values match each corresponding previous backtest.

| Combination  | TopN | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Mean daily cost |
| ------------ | ---: | -------------: | -------------: | -----------: | ---------: | --------------: |
| rank × axonx |    5 |         23.42% |        113.64% |      -40.21% |     0.7590 |           0.20% |
| rank × axonx |   10 |         14.00% |         60.43% |      -38.19% |     0.5502 |           0.20% |
| rank × axonx |   20 |          7.67% |         30.56% |      -38.65% |     0.3619 |           0.20% |
| rank × axonx |   30 |          0.97% |          3.53% |      -40.60% |     0.1308 |           0.20% |
| rank × qlib  |    5 |         12.04% |         50.71% |      -32.46% |     0.5000 |           0.20% |
| rank × qlib  |   10 |          4.65% |         17.81% |      -36.63% |     0.2604 |           0.20% |
| rank × qlib  |   20 |         -3.92% |        -13.44% |      -43.91% |    -0.0675 |           0.20% |
| rank × qlib  |   30 |         -6.01% |        -20.03% |      -42.31% |    -0.1576 |           0.20% |
| csz × axonx  |    5 |        -21.52% |        -58.28% |      -83.86% |    -0.2655 |           0.19% |
| csz × axonx  |   10 |        -16.39% |        -47.58% |      -74.10% |    -0.2833 |           0.20% |
| csz × axonx  |   20 |        -13.81% |        -41.49% |      -66.62% |    -0.2995 |           0.20% |
| csz × axonx  |   30 |        -15.75% |        -46.10% |      -62.22% |    -0.4028 |           0.20% |
| csz × qlib   |    5 |         -7.13% |        -23.41% |      -61.52% |    -0.0752 |           0.20% |
| csz × qlib   |   10 |         -0.92% |         -3.27% |      -50.27% |     0.0888 |           0.20% |
| csz × qlib   |   20 |         -6.28% |        -20.87% |      -54.03% |    -0.1085 |           0.20% |
| csz × qlib   |   30 |         -4.47% |        -15.21% |      -51.62% |    -0.0484 |           0.20% |

At these rates, rank × AxonX has positive net annualized returns at Top5/10/20/30: 23.42% / 14.00% / 7.67% / 0.97%. Other combinations are shown above. Every order fee was verified against its executed notional and side rate; unfilled orders pay zero fees. The normalized-cash ledger omits the RMB 5 minimum fee.

### Top20 fee comparison

| Combination  | 0.2% per side net annualized | 0.05% buy / 0.15% sell net annualized |
| ------------ | ---------------------------: | ------------------------------------: |
| rank × axonx |                      -34.69% |                                 7.67% |
| rank × qlib  |                      -41.81% |                                -3.92% |
| csz × axonx  |                      -47.47% |                               -13.81% |
| csz × qlib   |                      -43.15% |                                -6.28% |

### Yearly net annualized returns at 0.05% buy / 0.15% sell

| Combination  | Year |    Top5 |   Top10 |   Top20 |   Top30 |
| ------------ | ---- | ------: | ------: | ------: | ------: |
| rank × axonx | 2023 | -11.12% |  -5.84% |  -9.13% | -13.36% |
| rank × axonx | 2024 |  13.88% |  -6.02% |   5.06% |  -1.76% |
| rank × axonx | 2025 |  76.43% |  72.09% |  48.57% |  42.37% |
| rank × axonx | 2026 |  31.92% |   9.66% |  -9.31% | -18.88% |
| rank × qlib  | 2023 |  10.42% |   3.57% |  -3.55% |  -5.79% |
| rank × qlib  | 2024 |  -1.58% |  -8.52% | -18.92% | -14.90% |
| rank × qlib  | 2025 |  62.04% |  51.42% |  25.95% |  20.31% |
| rank × qlib  | 2026 | -17.07% | -22.53% | -16.55% | -23.08% |
| csz × axonx  | 2023 | -47.11% | -39.06% | -29.27% | -28.18% |
| csz × axonx  | 2024 | -62.63% | -53.44% | -47.21% | -40.87% |
| csz × axonx  | 2025 |  49.31% |  39.85% |  38.18% |  25.44% |
| csz × axonx  | 2026 |  50.69% |  39.50% |  14.57% |  -1.95% |
| csz × qlib   | 2023 | -32.42% | -17.28% | -26.47% | -18.72% |
| csz × qlib   | 2024 | -32.07% | -32.20% | -23.56% | -23.33% |
| csz × qlib   | 2025 |  36.02% |  68.95% |  50.00% |  39.75% |
| csz × qlib   | 2026 |  29.06% |   2.29% |  -9.47% |  -4.52% |

2026 covers only through October 8. All four runs still report `incomplete_market_data`; missing-data order counts below combine the four TopN sizes.

| Combination  | Missing-data orders |
| ------------ | ------------------: |
| rank × axonx |                  95 |
| rank × qlib  |                  26 |
| csz × axonx  |                 114 |
| csz × qlib   |                 104 |

### Backtest tasks at 0.05% buy / 0.15% sell

| Combination  | Task ID                                      | Run ID                             |
| ------------ | -------------------------------------------- | ---------------------------------- |
| rank × axonx | `backtest#qlib_a158_backtest#2026100913AKR6` | `b0edd311bfbe40e4b1a0f89af877a040` |
| rank × qlib  | `backtest#qlib_a158_backtest#2026100913zQxv` | `23bb1289a95c49a391b3391fbc40cd25` |
| csz × axonx  | `backtest#qlib_a158_backtest#2026100913haLH` | `3bebf907a9ce42bea767ddfeb7e88a60` |
| csz × qlib   | `backtest#qlib_a158_backtest#20261009139XZP` | `14793a7df8b5481baa24c432721e0b33` |

Plugin content SHA-256 for the asymmetric-fee backtests: `4820c52b1a9d175c56ee18f6726eecd162a37e88e278a19bce0d52bac8310ef0`.

Core source SHA-256 at execution: `engine.py: d641e3ba577ea5283ef8b6d4dc1d4598659b7b4c3971887026c586712f6bc2c1` `backtest.py: ab38d4e3afc25d552d52d6e8eec9b96cf6ac5a50f7cf2848cd81b7463bd16d62`.

## Baseline results at 0.2% per side

| Combination  | TopN | Gross annualized | Net annualized | Net cumulative | Max drawdown | Net Sharpe | Mean two-sided turnover |
| ------------ | ---: | ---------------: | -------------: | -------------: | -----------: | ---------: | ----------------------: |
| rank × axonx |    5 |          103.61% |        -25.17% |        -64.86% |      -70.36% |    -0.7294 |                 198.88% |
| rank × axonx |   10 |           88.18% |        -30.93% |        -73.68% |      -78.37% |    -1.1370 |                 199.07% |
| rank × axonx |   20 |           77.60% |        -34.69% |        -78.49% |      -81.26% |    -1.4155 |                 198.64% |
| rank × axonx |   30 |           66.67% |        -38.79% |        -82.98% |      -84.68% |    -1.6882 |                 198.84% |
| rank × qlib  |    5 |           84.95% |        -32.07% |        -75.22% |      -76.48% |    -1.2569 |                 198.93% |
| rank × qlib  |   10 |           72.69% |        -36.61% |        -80.69% |      -81.50% |    -1.6119 |                 198.98% |
| rank × qlib  |   20 |           58.68% |        -41.81% |        -85.82% |      -86.20% |    -1.9963 |                 199.11% |
| rank × qlib  |   30 |           55.28% |        -43.07% |        -86.90% |      -87.21% |    -2.1121 |                 199.13% |
| csz × axonx  |    5 |           28.08% |        -51.90% |        -92.87% |      -94.53% |    -1.2609 |                 194.47% |
| csz × axonx  |   10 |           36.56% |        -48.91% |        -91.13% |      -93.12% |    -1.5331 |                 195.13% |
| csz × axonx  |   20 |           41.32% |        -47.47% |        -90.20% |      -92.04% |    -1.7582 |                 196.39% |
| csz × axonx  |   30 |           38.43% |        -48.69% |        -90.99% |      -92.23% |    -1.9393 |                 196.92% |
| csz × qlib   |    5 |           53.03% |        -43.61% |        -87.34% |      -88.56% |    -1.5243 |                 198.15% |
| csz × qlib   |   10 |           63.39% |        -39.91% |        -84.07% |      -85.19% |    -1.5234 |                 198.56% |
| csz × qlib   |   20 |           54.59% |        -43.15% |        -86.96% |      -88.00% |    -1.7947 |                 198.52% |
| csz × qlib   |   30 |           57.60% |        -42.06% |        -86.04% |      -87.17% |    -1.7580 |                 198.59% |

Net Sharpe is computed from daily net returns after subtracting the compounded daily risk-free rate, with `ddof=1`.

Within this interval, both rank runs have higher OOS RankIC than the CSZ runs. AxonX parameters produce higher net returns at every TopN for rank; qlib parameters produce higher net returns at every TopN for CSZ. All 16 portfolios have negative net returns. Mean two-sided turnover is approximately 194%–199%, giving daily transaction costs of approximately 0.39%–0.40% at the current fee rate.

## Yearly baseline at 0.2% per side

| Combination  | Year | RankIC |    Top5 |   Top10 |   Top20 |   Top30 |
| ------------ | ---- | -----: | ------: | ------: | ------: | ------: |
| rank × axonx | 2023 | 0.0906 | -46.22% | -43.07% | -44.98% | -47.57% |
| rank × axonx | 2024 | 0.0915 | -30.77% | -42.88% | -36.07% | -40.27% |
| rank × axonx | 2025 | 0.1037 |   7.03% |   4.22% |  -9.87% | -13.69% |
| rank × axonx | 2026 | 0.0803 | -20.14% | -33.62% | -45.09% | -50.88% |
| rank × qlib  | 2023 | 0.0890 | -33.22% | -37.36% | -41.66% | -43.07% |
| rank × qlib  | 2024 | 0.0855 | -40.07% | -44.41% | -50.77% | -48.38% |
| rank × qlib  | 2025 | 0.1011 |  -1.84% |  -8.31% | -23.71% | -27.11% |
| rank × qlib  | 2026 | 0.0780 | -49.81% | -53.16% | -49.57% | -53.39% |
| csz × axonx  | 2023 | 0.0787 | -67.75% | -62.95% | -57.13% | -56.45% |
| csz × axonx  | 2024 | 0.0827 | -76.97% | -71.36% | -67.68% | -63.85% |
| csz × axonx  | 2025 | 0.0958 |  -7.99% | -14.40% | -15.53% | -23.50% |
| csz × axonx  | 2026 | 0.0734 |  -8.38% | -15.12% | -30.40% | -40.37% |
| csz × qlib   | 2023 | 0.0758 | -59.08% | -49.96% | -55.45% | -50.83% |
| csz × qlib   | 2024 | 0.0797 | -58.73% | -58.78% | -53.55% | -53.36% |
| csz × qlib   | 2025 | 0.0929 | -17.11% |   2.67% |  -9.00% | -15.21% |
| csz × qlib   | 2026 | 0.0693 | -21.81% | -38.11% | -45.13% | -42.15% |

2026 covers only through October 8; the table annualizes that partial interval.

## Baseline market completeness at 0.2% per side

All four runs report `incomplete_market_data`: some orders encounter absent quotes. Missing quotes carry previous marks and blocked exits retain capital. Counts below are `missing_data` order records across all four TopN sizes, not missing trading-day counts.

| Combination  | Missing-data orders |
| ------------ | ------------------: |
| rank × axonx |                  95 |
| rank × qlib  |                  26 |
| csz × axonx  |                 114 |
| csz × qlib   |                 104 |

## Tasks and provenance

| Stage                 | Task ID                                      | Run ID                             |
| --------------------- | -------------------------------------------- | ---------------------------------- |
| download              | `api#download_tushare_task#2026100912a399`   | `b3179a58b84847a88daaf4ec052967d2` |
| etl                   | `etl#qlib_a158_etl#2026100912u43E`           | `39c043a8d09f4ef3a1addef8b2861c3f` |
| rank × axonx train    | `train#qlib_a158_train#2026100912mMlp`       | `710de1c0530b430e94e0b92e7634cd2a` |
| rank × axonx predict  | `predict#qlib_a158_predict#2026100912Qanw`   | `c8b97e5ec7bb483da455d988ec6216d3` |
| rank × axonx backtest | `backtest#qlib_a158_backtest#2026100912OQf2` | `7ab3ef7b6f22489395542d27dd9e5ff7` |
| rank × qlib train     | `train#qlib_a158_train#2026100912DrPp`       | `2863b7e79aeb4a4fa85d384007fc89e1` |
| rank × qlib predict   | `predict#qlib_a158_predict#2026100912O65L`   | `84f7049f6d5c41f28ebc6b6296c0f453` |
| rank × qlib backtest  | `backtest#qlib_a158_backtest#2026100912bXkC` | `ce2d34cee7374d7baa5dfd8adaaa4eae` |
| csz × axonx train     | `train#qlib_a158_train#2026100912iEdd`       | `6ac99b6c2cde45338a839971d37851c8` |
| csz × axonx predict   | `predict#qlib_a158_predict#2026100912d0jv`   | `bb1c5eb5da324d84b98a2f218a6c794f` |
| csz × axonx backtest  | `backtest#qlib_a158_backtest#2026100912pNgu` | `8f2c0b332ea64b54bd7c72b448627c9b` |
| csz × qlib train      | `train#qlib_a158_train#2026100912glBz`       | `b03c2e40f31448aabc2d77ecd0b50fc8` |
| csz × qlib predict    | `predict#qlib_a158_predict#2026100912F9PU`   | `2222baa3b3194a59a64c9ddd492c7458` |
| csz × qlib backtest   | `backtest#qlib_a158_backtest#2026100912MRhB` | `d4ef64d8c3b5401081d9f175669b82ec` |

Plugin: `axonx-qlib-a158` 0.2.0; content SHA-256: `3a1ebeda40f151e085b15a8b65885229a90a0361a85719ecbb4d5bcf695d9b60`.

ETL dataset SHA-256: `0e12be1801f5d7ba9c3dab263c1a3a5e9905dc99b1b56bef0d168f0f80ba21cf`.

All four backtests have matching market, labels and calendar SHA-256 values. Runtime: Python 3.12.14, Polars 1.44.2, LightGBM 4.7.0 and AxonX 0.1.1. Full metadata and daily artifacts remain in the corresponding tasks on machine 45.

See the [holding-period experiment](HOLDING_PERIOD_RESULTS.md).
