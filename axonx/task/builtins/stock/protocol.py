"""Stock feature semantics shared by feature producers and model consumers."""

from ...protocol import fingerprint, task_protocol, validate_protocol
from ....enums import TaskType

FEATURE_IDENTITY_FIELDS = (
    "feature_family",
    "trade_time",
    "feature_cols",
    "default_feature_cols",
    "categorical_feature_cardinalities",
    "categorical_embedding_groups",
    "global_feature_groups",
    "return_unit",
    "bar_specs",
    "feature_winsorize_tail",
    "cross_section_reference_universe",
    "adj_factor_fill_policy",
    "feature_rules",
    "point_in_time_policy",
)


def validate_feature_protocol(metadata: dict) -> dict:
    validate_protocol(metadata, TaskType.ETL)
    required = {
        "feature_family",
        "trade_time",
        "feature_cols",
        "default_feature_cols",
        "global_feature_groups",
        "feature_rules",
    }
    if missing := required - metadata.keys():
        raise ValueError(f"Incomplete feature protocol: {sorted(missing)}")
    if not metadata["feature_family"]:
        raise ValueError("Feature protocol requires a family")
    return metadata


def feature_identity(metadata: dict) -> str:
    """Dates, locations, source files and quality counters are not feature semantics."""
    return fingerprint({key: metadata[key] for key in FEATURE_IDENTITY_FIELDS if key in metadata})


def feature_contract(metadata: dict) -> dict:
    """Retain model input semantics without ETL locations, dates or counters."""
    validate_feature_protocol(metadata)
    return {
        **task_protocol(TaskType.ETL),
        **{key: metadata[key] for key in FEATURE_IDENTITY_FIELDS if key in metadata},
    }
