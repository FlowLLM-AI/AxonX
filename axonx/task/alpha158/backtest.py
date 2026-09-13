"""Backtest an Alpha158 prediction task against realized one-day returns."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field, field_validator

from ...components.registry import R
from ...enums import TaskType
from ..base import BaseConfig, BaseTask, TaskStep
from ._artifacts import (
    artifact_path,
    artifact_record,
    atomic_output,
    metadata_header,
    read_metadata,
    task_directory,
    write_metadata,
)


class Alpha158BacktestConfig(BaseConfig):
    """Configure top-N portfolios for one Alpha158 prediction task."""

    prediction_task_id: str
    top_ns: str = "1,2,3,4,5,10,20,30,50"
    holdings_top_n: int = Field(default=50, gt=0, le=500)
    transaction_cost_rate: float = Field(default=0.002, ge=0.0, lt=1.0)
    annual_risk_free_rate: float = Field(default=0.012, gt=-1.0, lt=1.0)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.90, gt=0.0, le=1.0)

    @field_validator("top_ns")
    @classmethod
    def validate_top_ns(cls, value: str) -> str:
        values = cls.parse_top_ns(value)
        if len(values) != len(set(values)):
            raise ValueError("top_ns 不能重复")
        return ",".join(str(item) for item in values)

    @staticmethod
    def parse_top_ns(value: str) -> tuple[int, ...]:
        try:
            result = tuple(
                int(part.strip()) for part in value.split(",") if part.strip()
            )
        except ValueError as exc:
            raise ValueError("top_ns 必须是逗号分隔的正整数") from exc
        if not result or any(item <= 0 for item in result):
            raise ValueError("top_ns 必须是逗号分隔的正整数")
        return result


@R.register("alpha158_backtest")
class Alpha158BacktestTask(BaseTask):
    """Rank all predicted stocks daily and report IC plus gross, net, turnover, risk, and benchmark metrics."""

    REQUIRED_COLUMNS = ("trade_date", "ts_code", "pred", "actual_return", "label_valid")
    config_cls = Alpha158BacktestConfig
    config: Alpha158BacktestConfig
    task_type = TaskType.BACKTEST
    output_keys = (
        "daily_file",
        "holdings_file",
        "overall_file",
        "yearly_file",
        "quarterly_file",
        "metadata_file",
        "days",
    )

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_prediction_task
        yield self.load_and_validate_predictions
        yield self.calculate_daily_performance
        yield self.build_period_summaries
        yield self.write_outputs
        yield self.write_metadata
        yield self.publish_output

    def resolve_prediction_task(self) -> None:
        prediction_dir = task_directory(
            self.workspace_path, "predict", self.config.prediction_task_id
        )
        prediction_metadata_path = prediction_dir / "metadata.json"
        prediction_metadata = read_metadata(
            prediction_metadata_path, description="Alpha158 prediction"
        )
        if (
            prediction_metadata.get("protocol", {}).get("actual_return_column")
            != "label_1d"
        ):
            raise ValueError("回测只接受以原始 label_1d 为 actual_return 的预测任务")
        predictions_path = artifact_path(
            prediction_dir, prediction_metadata, "predictions"
        )
        output_dir = self.workspace_path / "backtest" / self.task_id
        self.context.update(
            prediction_metadata_path=prediction_metadata_path,
            prediction_metadata=prediction_metadata,
            predictions_path=predictions_path,
            output_dir=output_dir,
            daily_path=output_dir / "daily.csv",
            holdings_path=output_dir / "holdings.csv",
            overall_path=output_dir / "overall.csv",
            yearly_path=output_dir / "yearly.csv",
            quarterly_path=output_dir / "quarterly.csv",
            metadata_path=output_dir / "metadata.json",
            top_ns=Alpha158BacktestConfig.parse_top_ns(self.config.top_ns),
        )
        self.logger.info(
            f"Backtest source resolved prediction_task_id={self.config.prediction_task_id} "
            f"predictions={predictions_path} output_dir={output_dir}"
        )

    def load_and_validate_predictions(self) -> None:
        path: Path = self.context["predictions_path"]
        if not path.is_file():
            raise FileNotFoundError(f"预测文件不存在: {path}")
        frame = pd.read_parquet(path)
        if missing := [
            column for column in self.REQUIRED_COLUMNS if column not in frame
        ]:
            raise ValueError(f"预测文件缺少字段: {', '.join(missing)}")
        if frame.columns.duplicated().any():
            raise ValueError("预测文件包含重复字段")
        if frame.empty:
            raise ValueError("预测文件为空")
        if frame.duplicated(["trade_date", "ts_code"]).any():
            raise ValueError("预测文件包含重复的 trade_date, ts_code")
        frame = frame.copy()
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame["ts_code"] = frame["ts_code"].astype(str)
        if (
            pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
            .isna()
            .any()
        ):
            raise ValueError("trade_date 必须是有效 YYYYMMDD")
        for column in ("pred", "actual_return"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["label_valid"] = self._boolean(frame["label_valid"])
        if (frame["pred"].notna() & ~np.isfinite(frame["pred"])).any() or (
            frame["actual_return"].notna() & ~np.isfinite(frame["actual_return"])
        ).any():
            raise ValueError("pred 或 actual_return 包含非有限值")
        if frame.loc[frame["label_valid"], "actual_return"].isna().any():
            raise ValueError("label_valid=true 的行必须包含 actual_return")
        if (frame.loc[frame["label_valid"], "actual_return"] <= -1).any():
            raise ValueError("有效 actual_return 必须大于 -1")
        index_columns = tuple(
            column for column in frame if column.startswith("index_weight_")
        )
        for column in index_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            finite = frame[column].dropna()
            if (~np.isfinite(finite)).any() or (finite < 0).any():
                raise ValueError(f"{column} 必须是非负有限小数权重")
            if (
                frame.groupby("trade_date")[column].sum(min_count=1).dropna() > 1.05
            ).any():
                raise ValueError(f"{column} 每日合计不能明显超过 1")
        usable = (
            frame["label_valid"]
            & frame["pred"].notna()
            & frame["actual_return"].notna()
        )
        if not usable.any():
            raise ValueError("预测文件没有可回测的 label_1d 样本")
        self.context.update(
            frame=frame.sort_values(["trade_date", "ts_code"], kind="stable"),
            index_columns=index_columns,
        )
        self.logger.info(
            f"Backtest predictions validated rows={len(frame)} usable_rows={int(usable.sum())} "
            f"dates={frame['trade_date'].nunique()} indices={len(index_columns)}"
        )

    @staticmethod
    def _boolean(values: pd.Series) -> pd.Series:
        mapping = {True: True, False: False, "true": True, "false": False}
        normalized = values.map(
            lambda value: mapping.get(value.strip().lower())
            if isinstance(value, str)
            else mapping.get(value),
        )
        if normalized.isna().any():
            raise ValueError("label_valid 只能包含 bool、0/1 或 true/false")
        return normalized.astype(bool)

    def calculate_daily_performance(self) -> None:
        rows: list[dict[str, Any]] = []
        holding_rows: list[dict[str, Any]] = []
        previous: dict[int, dict[str, float]] = {}
        net_values = {top_n: 1.0 for top_n in self.context["top_ns"]}
        grouped = self.context["frame"].groupby("trade_date", sort=True)
        total = grouped.ngroups
        for index, (trade_date, all_rows) in enumerate(grouped, start=1):
            candidates = all_rows[
                all_rows["label_valid"]
                & all_rows["pred"].notna()
                & all_rows["actual_return"].notna()
            ].sort_values(["pred", "ts_code"], ascending=[False, True], kind="stable")
            if candidates.empty:
                continue
            row: dict[str, Any] = {
                "trade_date": trade_date,
                "candidates": len(candidates),
                "ic": self._correlation(
                    candidates["pred"], candidates["actual_return"], "pearson"
                ),
                "rank_ic": self._correlation(
                    candidates["pred"], candidates["actual_return"], "spearman"
                ),
                "benchmark_universe": float(candidates["actual_return"].mean()),
            }
            self._add_index_returns(row, all_rows)
            holdings = candidates.head(self.config.holdings_top_n)
            holding_weight = 1.0 / len(holdings)
            for rank, (_, holding) in enumerate(holdings.iterrows(), start=1):
                holding_rows.append(
                    {
                        "trade_date": trade_date,
                        "rank": rank,
                        "ts_code": holding["ts_code"],
                        "prediction": float(holding["pred"]),
                        "weight": holding_weight,
                        "daily_return": float(holding["actual_return"]),
                    }
                )
            for top_n in self.context["top_ns"]:
                selected = candidates.head(top_n)
                weights = {code: 1.0 / len(selected) for code in selected["ts_code"]}
                turnover = (
                    0.0
                    if top_n not in previous
                    else self._turnover(previous[top_n], weights)
                )
                gross = float(selected["actual_return"].mean())
                cost = turnover * self.config.transaction_cost_rate
                net = gross - cost
                if net <= -1:
                    raise ValueError(f"{trade_date} Top{top_n} 扣费后收益不大于 -100%")
                net_values[top_n] *= 1 + net
                prefix = f"top{top_n}"
                row.update(
                    {
                        f"{prefix}_count": len(selected),
                        f"{prefix}_gross_return": gross,
                        f"{prefix}_turnover": turnover,
                        f"{prefix}_transaction_cost": cost,
                        f"{prefix}_net_return": net,
                        f"{prefix}_net_value": net_values[top_n],
                    },
                )
                previous[top_n] = weights
            rows.append(row)
            if index == 1 or index % 50 == 0 or index == total:
                self.report_progress(index / total * 95)
        if not rows:
            raise ValueError("没有可计算的回测交易日")
        self.context["daily"] = (
            pd.DataFrame(rows)
            .sort_values("trade_date", kind="stable")
            .reset_index(drop=True)
        )
        self.context["holdings"] = pd.DataFrame(
            holding_rows,
            columns=(
                "trade_date",
                "rank",
                "ts_code",
                "prediction",
                "weight",
                "daily_return",
            ),
        )
        self.logger.info(
            f"Daily backtest completed days={len(rows)} start={rows[0]['trade_date']} end={rows[-1]['trade_date']}"
        )

    def _add_index_returns(self, row: dict[str, Any], frame: pd.DataFrame) -> None:
        for column in self.context["index_columns"]:
            name = column.removeprefix("index_weight_")
            weights = frame[column]
            valid = (
                frame["label_valid"] & frame["actual_return"].notna() & weights.notna()
            )
            covered = float(weights.where(valid, 0.0).sum())
            row[f"benchmark_{name}_coverage"] = min(covered, 1.0)
            row[f"benchmark_{name}"] = (
                float(
                    (
                        weights.where(valid, 0.0) * frame["actual_return"].fillna(0.0)
                    ).sum()
                    / covered
                )
                if covered >= self.config.minimum_index_weight_coverage
                else math.nan
            )

    def build_period_summaries(self) -> None:
        daily: pd.DataFrame = self.context["daily"]
        dated = daily.assign(
            year=daily["trade_date"].str[:4],
            quarter=pd.PeriodIndex(
                pd.to_datetime(daily["trade_date"], format="%Y%m%d"), freq="Q"
            ).astype(str),
        )
        self.context["overall"] = self._summarize_groups((("overall", daily),))
        self.context["yearly"] = self._summarize_groups(
            dated.groupby("year", sort=True)
        )
        self.context["quarterly"] = self._summarize_groups(
            dated.groupby("quarter", sort=True)
        )

    def _summarize_groups(self, groups) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for period, frame in groups:
            self._metric(rows, str(period), "all", "none", "trading_days", len(frame))
            self._metric(
                rows, str(period), "all", "none", "ic_mean", frame["ic"].mean()
            )
            self._metric(
                rows, str(period), "all", "none", "icir", self._ratio(frame["ic"])
            )
            self._metric(
                rows, str(period), "all", "none", "rankic_mean", frame["rank_ic"].mean()
            )
            self._metric(
                rows,
                str(period),
                "all",
                "none",
                "rankicir",
                self._ratio(frame["rank_ic"]),
            )
            benchmarks = ("benchmark_universe",) + tuple(
                f"benchmark_{column.removeprefix('index_weight_')}"
                for column in self.context["index_columns"]
            )
            for top_n in self.context["top_ns"]:
                prefix = f"top{top_n}"
                gross = frame[f"{prefix}_gross_return"]
                net = frame[f"{prefix}_net_return"]
                metrics = {
                    "gross_cumulative_return": float(gross.sum()),
                    "net_cumulative_return": float((1 + net).prod() - 1),
                    "annualized_net_return": self._annualized_return(net),
                    "annualized_volatility": float(
                        net.std(ddof=1) * math.sqrt(self.config.annualization_days)
                    ),
                    "sharpe": self._sharpe(net),
                    "max_drawdown": self._max_drawdown(net),
                    "win_rate": float((net > 0).mean()),
                    "average_turnover": float(frame[f"{prefix}_turnover"].mean()),
                    "average_holding_count": float(frame[f"{prefix}_count"].mean()),
                }
                for name, value in metrics.items():
                    self._metric(rows, str(period), prefix, "none", name, value)
                for benchmark in benchmarks:
                    if benchmark not in frame:
                        continue
                    aligned = pd.concat((net, frame[benchmark]), axis=1).dropna()
                    if aligned.empty:
                        continue
                    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
                    self._metric(
                        rows,
                        str(period),
                        prefix,
                        benchmark,
                        "active_cumulative_return",
                        float(active.sum()),
                    )
                    self._metric(
                        rows,
                        str(period),
                        prefix,
                        benchmark,
                        "information_ratio",
                        self._ratio(active) * math.sqrt(self.config.annualization_days),
                    )
        return pd.DataFrame(
            rows, columns=("period", "portfolio", "benchmark", "metric", "value")
        )

    @staticmethod
    def _metric(rows, period, portfolio, benchmark, metric, value) -> None:
        value = float(value)
        if np.isfinite(value):
            rows.append(
                {
                    "period": period,
                    "portfolio": portfolio,
                    "benchmark": benchmark,
                    "metric": metric,
                    "value": value,
                },
            )

    @staticmethod
    def _correlation(left: pd.Series, right: pd.Series, method: str) -> float:
        if len(left) < 2 or left.nunique() < 2 or right.nunique() < 2:
            return 0.0
        value = left.corr(right, method=method)
        return float(value) if pd.notna(value) and np.isfinite(value) else 0.0

    @staticmethod
    def _turnover(previous: dict[str, float], current: dict[str, float]) -> float:
        return 0.5 * sum(
            abs(current.get(code, 0.0) - previous.get(code, 0.0))
            for code in previous.keys() | current.keys()
        )

    @staticmethod
    def _ratio(values: pd.Series) -> float:
        values = values.dropna()
        std = values.std(ddof=1)
        return (
            float(values.mean() / std)
            if len(values) > 1 and pd.notna(std) and std > 0
            else 0.0
        )

    def _sharpe(self, returns: pd.Series) -> float:
        daily_rf = (1 + self.config.annual_risk_free_rate) ** (
            1 / self.config.annualization_days
        ) - 1
        return self._ratio(returns - daily_rf) * math.sqrt(
            self.config.annualization_days
        )

    def _annualized_return(self, returns: pd.Series) -> float:
        if returns.empty:
            return 0.0
        cumulative = float((1 + returns).prod())
        return (
            cumulative ** (self.config.annualization_days / len(returns)) - 1
            if cumulative > 0
            else -1.0
        )

    @staticmethod
    def _max_drawdown(returns: pd.Series) -> float:
        net = (1 + returns).cumprod()
        return float((net / net.cummax() - 1).min()) if not net.empty else 0.0

    def write_outputs(self) -> None:
        output_dir: Path = self.context["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        for key, path_key in (
            ("daily", "daily_path"),
            ("holdings", "holdings_path"),
            ("overall", "overall_path"),
            ("yearly", "yearly_path"),
            ("quarterly", "quarterly_path"),
        ):
            path: Path = self.context[path_key]
            atomic_output(
                path,
                lambda temporary, frame=self.context[key]: frame.to_csv(
                    temporary, index=False
                ),
            )
        self.logger.info(
            f"Backtest CSV outputs written daily={self.context['daily_path']} overall={self.context['overall_path']}"
        )

    def write_metadata(self) -> None:
        output_dir: Path = self.context["output_dir"]
        metadata = {
            **metadata_header(
                task_name="alpha158_backtest",
                task_id=self.task_id,
                task_type=self.task_type.value,
            ),
            "config": self.config.model_dump(
                mode="json", exclude={"task_id", "task_type"}
            ),
            "source": {
                "prediction_task_id": self.config.prediction_task_id,
                "prediction_metadata": str(self.context["prediction_metadata_path"]),
                "training_task_id": self.context["prediction_metadata"]
                .get("source", {})
                .get("training_task_id"),
            },
            "protocol": {
                "actual_return": "raw label_1d decimal adjusted-close return",
                "candidate_filter": "finite prediction and valid label_1d; no tradeability filter",
                "portfolio": "daily equal-weight top-N ranked by descending prediction",
                "initial_turnover": 0.0,
                "turnover": "half L1 distance between consecutive target portfolios",
                "net_return": "gross return minus turnover times transaction_cost_rate",
                "ic": "daily Pearson correlation between prediction and raw label_1d",
                "rank_ic": "daily Spearman correlation between prediction and raw label_1d",
            },
            "date_range": {
                "start": self.context["daily"]["trade_date"].min(),
                "end": self.context["daily"]["trade_date"].max(),
            },
            "days": len(self.context["daily"]),
            "index_weight_columns": list(self.context["index_columns"]),
            "artifacts": {
                name: f"{name}.csv"
                for name in ("daily", "holdings", "overall", "yearly", "quarterly")
            },
            "artifact_integrity": {
                name: artifact_record(self.context[f"{name}_path"], output_dir)
                for name in ("daily", "holdings", "overall", "yearly", "quarterly")
            },
        }
        write_metadata(self.context["metadata_path"], metadata)

    def publish_output(self) -> None:
        self.context.update(
            daily_file=str(self.context["daily_path"]),
            holdings_file=str(self.context["holdings_path"]),
            overall_file=str(self.context["overall_path"]),
            yearly_file=str(self.context["yearly_path"]),
            quarterly_file=str(self.context["quarterly_path"]),
            metadata_file=str(self.context["metadata_path"]),
            days=len(self.context["daily"]),
        )
