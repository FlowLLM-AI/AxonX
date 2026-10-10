"""Compare Alpha158 labels and LightGBM presets using one local ETL."""

import argparse
import json
import math
from pathlib import Path

import polars as pl
from axonx_qlib_a158.backtest import Alpha158BacktestTask
from axonx_qlib_a158.predict import LgbmPredictTask
from axonx_qlib_a158.train import LgbmTrainTask

from axonx.enums import TaskState
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage import read_metadata
from axonx.task.storage.workspace import task_path
from axonx.utils.fs import atomic_write, file_sha256


def run_comparison(options: argparse.Namespace) -> dict:
    """Run the selected label/preset combinations and save metrics with task provenance."""
    workspace = options.workspace_path.resolve()
    metadata = read_metadata(task_path(workspace, options.etl_task) / "metadata.json")
    dataset = metadata["output_params"]["artifacts"]["dataset"]
    records, summaries = {}, []

    def run(cls, name, **params):
        task = cls(params, workspace_path=workspace, reg_name=name)
        status = TaskRunner().run(task)
        if status.state != TaskState.SUCCEEDED:
            raise RuntimeError(f"{task.task_id}: {status.error}")
        return task.task_id, status.result

    labels = list(dict.fromkeys(options.labels))
    combinations = [(label, preset) for label in labels for preset in ("axonx", "qlib")]
    for label, preset in combinations:
        key = preset if len(labels) == 1 else f"{label}_{preset}"
        train_id, train = run(
            LgbmTrainTask,
            "qlib_a158_train",
            source_tasks=options.etl_task,
            parameter_preset=preset,
            label_column=f"label_return_{label}",
            train_start=options.train_start,
            train_end=options.train_end,
            num_threads=options.num_threads,
            num_boost_round=options.num_boost_round,
        )
        predict_id, prediction = run(
            LgbmPredictTask,
            "qlib_a158_predict",
            source_tasks=train_id,
            pred_start=options.pred_start,
            pred_end=options.pred_end,
        )
        backtest_id, backtest = run(
            Alpha158BacktestTask,
            "qlib_a158_backtest",
            source_tasks=predict_id,
            top_ns=options.top_ns,
            as_of_date=prediction["date_range"]["end"],
            transaction_cost_rate=options.transaction_cost_rate,
            buy_cost_rate=options.buy_cost_rate,
            sell_cost_rate=options.sell_cost_rate,
        )
        records[key] = {
            "label": label,
            "parameter_preset": preset,
            "backtest_settings": backtest["protocol"]["settings"],
            "tasks": {"train": train_id, "predict": predict_id, "backtest": backtest_id},
            "parameters": train["parameters"],
            "best_iteration": train["best_iteration"],
            "validation_metrics": {
                key: value if value is not None and math.isfinite(value) else None
                for key, value in train["validation_metrics"].items()
            },
            "evaluation_status": backtest["evaluation_status"],
            "input_sha256": backtest["protocol"]["input_sha256"],
        }
        summaries.append(
            pl.read_parquet(backtest["summary_file"]).with_columns(
                pl.lit(preset).alias("preset"),
                pl.lit(label).alias("label"),
            )
        )
    result = {
        "etl_task": options.etl_task,
        "dataset_sha256": dataset["sha256"],
        "settings": {key: str(value) if isinstance(value, Path) else value for key, value in vars(options).items()},
        "presets": records,
        "selection": "Validation metrics, yearly summaries, transaction costs and evaluation status.",
    }
    # Models and predictions differ, but market/calendar/labels must be identical.
    for key in ("market", "calendar", "labels"):
        digests = {record["input_sha256"].get(key) for record in records.values()}
        if len(digests) != 1:
            raise ValueError(f"Comparison inputs differ: {key}")
    source = task_path(workspace, options.etl_task) / dataset["path"]
    if file_sha256(source) != dataset["sha256"]:
        raise ValueError("ETL dataset changed during parameter comparison")
    output = workspace / "qlib_a158_comparison" / train_id.split("#")[-1]
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "summary.csv", pl.concat(summaries).write_csv)
    atomic_write(
        output / "comparison.json", lambda path: path.write_text(json.dumps(result, indent=2, allow_nan=False))
    )
    return {"output_dir": str(output), **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-path", type=Path, default=Path(".axonx"))
    parser.add_argument("--etl-task", required=True)
    parser.add_argument("--labels", choices=["rank", "csz"], nargs="+", default=["rank"])
    parser.add_argument("--buy-cost-rate", type=float, default=None)
    parser.add_argument("--sell-cost-rate", type=float, default=None)
    parser.add_argument("--train-start", default="20150101")
    parser.add_argument("--train-end", default="20230101")
    parser.add_argument("--pred-start", default="20230101")
    parser.add_argument("--pred-end", default=None)
    parser.add_argument("--num-threads", type=int, default=8)
    parser.add_argument("--num-boost-round", type=int, default=1000)
    parser.add_argument("--top-ns", type=int, nargs="+", default=[5, 10, 20, 30])
    parser.add_argument("--transaction-cost-rate", type=float, default=0.002)
    print(json.dumps(run_comparison(parser.parse_args()), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
