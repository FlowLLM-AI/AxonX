"""Qlib Alpha158 reference, parameter presets and AxonX workflow differences.

AxonX executes the workflow with Polars features and LightGBM models.
The reference is examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
and its Alpha158 handler at Qlib commit 54355232463878d2eebb91fe0ee5fa7fa1f5976c.
"""

QLIB_REFERENCE = {
    "repository": "microsoft/qlib",
    "commit": "54355232463878d2eebb91fe0ee5fa7fa1f5976c",
    "workflow": "examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml",
}

# Qlib aliases colsample_bytree/subsample are represented by their canonical
# LightGBM names. Its workflow does not enable subsample_freq, so bagging stays
# disabled even with subsample < 1. The qlib preset uses bagging_freq=0.
QLIB_PARAMETERS = {
    "learning_rate": 0.2,
    "num_leaves": 210,
    "max_depth": 8,
    "feature_fraction": 0.8879,
    "bagging_fraction": 0.8789,
    "bagging_freq": 0,
    "lambda_l1": 205.6999,
    "lambda_l2": 580.9768,
}

DEVIATIONS = {
    "universe": (
        "Shanghai/Shenzhen stocks excluding Beijing; training uses signal-buyable rows. "
        "The Qlib example uses historical CSI300 members."
    ),
    "features": (
        "Same 158 families/windows; skip absent high/low observations for extrema indices "
        "rather than numpy argmax NaN behavior."
    ),
    "data": "Tushare adjusted prices and volume; Qlib uses its data snapshot and collector normalization.",
    "label": "Signal close to next market close; daily rank by default, not Qlib T+1/T+2 return with sample-std CSZ.",
    "training": (
        "Cutoff-safe eligible rows, tail trimming, last 10% of dates for early stopping, then "
        "refit all training dates."
    ),
    "execution": (
        "Same-close quote proxy, not next-day execution; after-close features do not "
        "guarantee that fill in live trading."
    ),
    "limits": "Official board-specific daily price limits with fallback, not a uniform 9.5% change threshold.",
    "strategy": (
        "Fixed holding expiry and TopN cash ledger, not TopkDropout/95% cash allocation; "
        "retention belongs to the strategy plugin."
    ),
    "evaluation": (
        "Compound net equity and 252-day annualization; constituent-weighted HS300 is a "
        "proxy, not the index quote series."
    ),
}
