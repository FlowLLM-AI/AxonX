"""Reusable cross-sectional ranking backtest task."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field, field_validator

from ..base_task import BaseConfig, BaseTask, TaskStep
from ...components.component_registry import R
from ...enumeration import TaskType


class RankingBacktestConfig(BaseConfig):
    """Configure a ranking backtest over a prediction-result parquet file.

    Optional benchmark weights are discovered from ``index_weight_*`` columns,
    for example ``index_weight_hs300``. Weights use decimal units; confirmed
    non-members use zero, while unavailable weight data uses null. Benchmark
    returns renormalize usable weights when their coverage meets the threshold.
    """

    input_file: Path
    output_dir: Path
    top_ns: str = "1,2,3,4,5,10,20,30"
    transaction_cost_rate: float = Field(default=0.002, ge=0.0, lt=1.0)
    annual_risk_free_rate: float = Field(default=0.012, gt=-1.0, lt=1.0)
    annualization_days: int = Field(default=252, gt=0)
    minimum_index_weight_coverage: float = Field(default=0.90, gt=0.0, le=1.0)
    return_unit: Literal["decimal", "percent"] = "decimal"
    return_horizon: str = "unspecified"
    plot_report: bool = True

    @field_validator("top_ns")
    @classmethod
    def validate_top_ns(cls, value: str) -> str:
        values = cls.parse_positive_ints(value)
        if len(values) != len(set(values)):
            raise ValueError("top_ns 不能重复")
        return ",".join(str(item) for item in values)

    @staticmethod
    def parse_positive_ints(value: str) -> tuple[int, ...]:
        try:
            values = tuple(int(part.strip()) for part in value.split(",") if part.strip())
        except ValueError as exc:
            raise ValueError("top_ns 必须是逗号分隔的正整数") from exc
        if not values or any(item <= 0 for item in values):
            raise ValueError("top_ns 必须是逗号分隔的正整数")
        return values


@R.register("ranking_backtest")
class RankingBacktestTask(BaseTask):
    """Calculate ranking quality, portfolio performance, and benchmark-relative metrics.

    Index weights are optional decimal columns named ``index_weight_<benchmark>``,
    such as ``index_weight_hs300``; all matching columns are discovered automatically.
    """

    REQUIRED_COLUMNS = (
        "trade_date",
        "ts_code",
        "pred",
        "actual_return",
        "label_valid",
        "is_model_candidate",
        "is_buyable_at_signal",
    )

    config_cls = RankingBacktestConfig
    config: RankingBacktestConfig
    task_type = TaskType.BACKTEST
    output_keys = (
        "status",
        "output_dir",
        "daily_file",
        "overall_file",
        "yearly_file",
        "quarterly_file",
        "report_file",
        "metadata_file",
    )

    def build_task_steps(self) -> Iterable[TaskStep]:
        yield self.resolve_paths
        yield self.load_and_validate
        yield self.calculate_daily
        yield self.build_summaries
        yield self.save_outputs
        if self.config.plot_report:
            yield self.plot_report
        yield self.save_metadata
        yield self.publish_output

    def resolve_paths(self) -> None:
        input_file = self.resolve_workspace_path(self.config.input_file)
        output_dir = self.resolve_workspace_path(self.config.output_dir)
        self.context.update(
            input_file=input_file,
            output_dir=output_dir,
            daily_path=output_dir / "daily.parquet",
            overall_path=output_dir / "overall.csv",
            yearly_path=output_dir / "yearly.csv",
            quarterly_path=output_dir / "quarterly.csv",
            report_path=output_dir / "backtest.pdf",
            metadata_path=output_dir / "metadata.json",
            top_ns=RankingBacktestConfig.parse_positive_ints(self.config.top_ns),
        )

    def load_and_validate(self) -> None:
        input_file = self.context["input_file"]
        if not input_file.is_file():
            raise FileNotFoundError(f"回测输入不存在: {input_file}")
        frame = pd.read_parquet(input_file)
        missing = [column for column in self.REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"回测输入缺少字段: {', '.join(missing)}")
        if frame.columns.duplicated().any():
            duplicates = sorted(set(frame.columns[frame.columns.duplicated()].tolist()))
            raise ValueError(f"回测输入字段重复: {', '.join(duplicates)}")
        if frame.empty:
            raise ValueError("回测输入为空")
        if frame.duplicated(["trade_date", "ts_code"]).any():
            raise ValueError("回测输入 trade_date, ts_code 主键重复")

        frame = frame.copy()
        frame["trade_date"] = frame["trade_date"].astype(str)
        frame["ts_code"] = frame["ts_code"].astype(str)
        for value in frame["trade_date"].unique():
            try:
                datetime.strptime(value, "%Y%m%d")
            except ValueError as exc:
                raise ValueError(f"trade_date 必须是有效 YYYYMMDD: {value}") from exc
        for column in ("label_valid", "is_model_candidate", "is_buyable_at_signal"):
            if frame[column].isna().any():
                raise ValueError(f"{column} 不能包含空值")
            frame[column] = self.normalize_boolean(frame[column], column)
        for column in ("pred", "actual_return"):
            values = pd.to_numeric(frame[column], errors="coerce")
            invalid = frame[column].notna() & ~np.isfinite(values)
            if invalid.any():
                raise ValueError(f"{column} 包含非有限值")
            frame[column] = values
        if self.config.return_unit == "percent":
            frame["actual_return"] /= 100.0
        invalid_label = frame["label_valid"] & frame["actual_return"].isna()
        if invalid_label.any():
            raise ValueError("label_valid=true 的记录必须包含 actual_return")
        if (frame.loc[frame["label_valid"], "actual_return"] <= -1.0).any():
            raise ValueError("有效 actual_return 必须大于 -1")

        index_columns = tuple(column for column in frame if column.startswith("index_weight_"))
        index_names = tuple(column.removeprefix("index_weight_") for column in index_columns)
        reserved_names = sorted(set(index_names) & {"", "none", "universe"})
        if reserved_names:
            raise ValueError(f"指数权重名称为空或与保留基准冲突: {', '.join(reserved_names)}")
        if len(index_names) != len(set(index_names)):
            raise ValueError("清理后的指数权重名称必须唯一")
        for column in index_columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            invalid = frame[column].notna() & ~np.isfinite(values)
            if invalid.any():
                raise ValueError(f"{column} 必须是非负有限小数权重")
            frame[column] = values
            finite = values.dropna()
            if (~np.isfinite(finite)).any() or (finite < 0).any():
                raise ValueError(f"{column} 必须是非负有限小数权重")
            daily_totals = frame.groupby("trade_date")[column].sum(min_count=1).dropna()
            if (daily_totals > 1.05).any():
                raise ValueError(f"{column} 必须使用小数权重，且每日合计不能明显超过 1")

        model_rows = frame["label_valid"] & frame["is_model_candidate"] & frame["pred"].notna()
        eligible_rows = model_rows & frame["is_buyable_at_signal"]
        if not model_rows.any() or not eligible_rows.any():
            raise ValueError("模型评价或可买 TopN 过滤后没有样本")
        self.context.update(
            frame=frame.sort_values(["trade_date", "ts_code"], kind="stable"),
            index_columns=index_columns,
            index_names=dict(zip(index_columns, index_names, strict=True)),
        )

    @staticmethod
    def normalize_boolean(values: pd.Series, column: str) -> pd.Series:
        """Normalize an explicit bool/0/1 representation and reject ambiguous truthiness."""
        normalized: list[bool] = []
        string_values = {"true": True, "false": False, "1": True, "0": False}
        for value in values:
            if isinstance(value, (bool, np.bool_)):
                normalized.append(bool(value))
            elif isinstance(value, (int, float, np.integer, np.floating)) and value in (0, 1):
                normalized.append(bool(value))
            elif isinstance(value, str) and value.strip().lower() in string_values:
                normalized.append(string_values[value.strip().lower()])
            else:
                raise ValueError(f"{column} 只能包含布尔值、0/1 或 true/false 字符串: {value!r}")
        return pd.Series(normalized, index=values.index, dtype=bool)

    def calculate_daily(self) -> None:
        rows: list[dict[str, Any]] = []
        previous_weights: dict[int, dict[str, float]] = {}
        net_values = {top_n: 1.0 for top_n in self.context["top_ns"]}
        for trade_date, all_rows in self.context["frame"].groupby("trade_date", sort=True):
            model = all_rows[all_rows["label_valid"] & all_rows["is_model_candidate"] & all_rows["pred"].notna()]
            eligible = model[model["is_buyable_at_signal"]].sort_values(
                ["pred", "ts_code"],
                ascending=[False, True],
                kind="stable",
            )
            if model.empty or eligible.empty:
                continue
            row: dict[str, Any] = {
                "trade_date": trade_date,
                "candidates": len(model),
                "buyable_candidates": len(eligible),
                "ic": self.safe_correlation(model["pred"], model["actual_return"], method="pearson"),
                "rank_ic": self.safe_correlation(model["pred"], model["actual_return"], method="spearman"),
                "benchmark_universe": float(model["actual_return"].mean()),
            }
            self.add_index_returns(row, all_rows)
            for top_n in self.context["top_ns"]:
                selected = eligible.head(top_n)
                selected_count = len(selected)
                weights = {code: 1.0 / selected_count for code in selected["ts_code"]}
                turnover = (
                    0.0 if top_n not in previous_weights else self.portfolio_turnover(previous_weights[top_n], weights)
                )
                gross_return = float(selected["actual_return"].mean())
                cost = turnover * self.config.transaction_cost_rate
                net_return = gross_return - cost
                net_values[top_n] *= 1.0 + net_return
                prefix = f"top{top_n}"
                row.update(
                    {
                        f"{prefix}_gross_return": gross_return,
                        f"{prefix}_turnover": turnover,
                        f"{prefix}_transaction_cost": cost,
                        f"{prefix}_net_return": net_return,
                        f"{prefix}_net_value": net_values[top_n],
                    },
                )
                previous_weights[top_n] = weights
            rows.append(row)
        if not rows:
            raise ValueError("没有同时包含有效模型样本和可买样本的交易日")
        self.context["daily"] = pd.DataFrame(rows).sort_values("trade_date", kind="stable").reset_index(drop=True)

    def add_index_returns(self, row: dict[str, Any], frame: pd.DataFrame) -> None:
        for column in self.context["index_columns"]:
            name = self.context["index_names"][column]
            weights = frame[column]
            total_weight = float(weights.sum(skipna=True))
            valid_return = frame["label_valid"] & frame["actual_return"].notna() & weights.notna()
            covered_weight = float(weights.where(valid_return, 0.0).sum())
            coverage = min(covered_weight, 1.0)
            row[f"benchmark_{name}_coverage"] = coverage
            row[f"benchmark_{name}"] = (
                float((weights.where(valid_return, 0.0) * frame["actual_return"].fillna(0.0)).sum() / covered_weight)
                if total_weight > 0.0 and coverage >= self.config.minimum_index_weight_coverage
                else math.nan
            )

    def build_summaries(self) -> None:
        """Build compact overall, yearly, and quarterly summaries from the daily detail table."""
        daily: pd.DataFrame = self.context["daily"]
        dated = daily.assign(
            year=daily["trade_date"].str[:4],
            quarter=pd.PeriodIndex(pd.to_datetime(daily["trade_date"], format="%Y%m%d"), freq="Q").astype(str),
        )
        overall: list[dict[str, Any]] = []
        yearly: list[dict[str, Any]] = []
        quarterly: list[dict[str, Any]] = []
        self.add_period_metrics(overall, "overall", daily)
        for year, frame in dated.groupby("year", sort=True):
            self.add_period_metrics(yearly, str(year), frame)
        for quarter, frame in dated.groupby("quarter", sort=True):
            self.add_period_metrics(quarterly, str(quarter), frame)
        columns = ("period", "portfolio", "benchmark", "metric", "value")
        summaries = {
            "overall": pd.DataFrame(overall, columns=columns),
            "yearly": pd.DataFrame(yearly, columns=columns),
            "quarterly": pd.DataFrame(quarterly, columns=columns),
        }
        for name, frame in summaries.items():
            finite = frame["value"].dropna()
            if not np.isfinite(finite).all():
                raise FloatingPointError(f"{name} metrics 包含非有限值")
        self.context.update(summaries)

    def add_period_metrics(
        self,
        output: list[dict[str, Any]],
        period: str,
        frame: pd.DataFrame,
    ) -> None:
        correlation_metrics = {"ic": ("IC均值", "IC比率"), "rank_ic": ("RankIC均值", "RankIC比率")}
        for name, labels in correlation_metrics.items():
            values = frame[name].dropna()
            self.metric(output, period, "all", "none", labels[0], values.mean())
            self.metric(output, period, "all", "none", labels[1], self.ratio(values))
        self.metric(output, period, "all", "none", "交易日数", len(frame))
        self.metric(output, period, "all", "none", "样本数", frame["candidates"].sum())
        for benchmark in self.benchmark_names():
            self.metric(
                output,
                period,
                "all",
                benchmark,
                "基准算术累计收益",
                frame[f"benchmark_{benchmark}"].sum(),
            )
            coverage_key = f"benchmark_{benchmark}_coverage"
            if coverage_key in frame:
                self.metric(output, period, "all", benchmark, "指数权重平均覆盖率", frame[coverage_key].mean())
        for top_n in self.context["top_ns"]:
            portfolio = f"top{top_n}"
            gross = frame[f"{portfolio}_gross_return"]
            net = frame[f"{portfolio}_net_return"]
            values = {
                "算术累计毛收益": gross.sum(),
                "扣费复利累计净收益": self.compounded_return(net),
                "毛收益夏普比率": self.sharpe(gross),
                "净收益夏普比率": self.sharpe(net),
                "毛收益年化波动率": self.annualized_volatility(gross),
                "净收益年化波动率": self.annualized_volatility(net),
                "毛收益算术最大回撤": self.arithmetic_max_drawdown(gross),
                "扣费净收益最大回撤": self.max_drawdown(net),
                "毛收益胜率": (gross > 0).mean(),
                "净收益胜率": (net > 0).mean(),
                "平均换手率": frame[f"{portfolio}_turnover"].mean(),
                "平均交易成本": frame[f"{portfolio}_transaction_cost"].mean(),
            }
            for metric, value in values.items():
                self.metric(output, period, portfolio, "none", metric, value)
            for benchmark in self.benchmark_names():
                baseline = frame[f"benchmark_{benchmark}"]
                self.metric(
                    output,
                    period,
                    portfolio,
                    benchmark,
                    "毛收益信息比率",
                    self.information_ratio(gross, baseline),
                )
                self.metric(
                    output,
                    period,
                    portfolio,
                    benchmark,
                    "净收益信息比率",
                    self.information_ratio(net, baseline),
                )

    def benchmark_names(self) -> tuple[str, ...]:
        return ("universe", *self.context["index_names"].values())

    @staticmethod
    def metric(
        output: list[dict[str, Any]],
        period: str,
        portfolio: str,
        benchmark: str,
        metric: str,
        value: Any,
    ) -> None:
        output.append(
            {
                "period": period,
                "portfolio": portfolio,
                "benchmark": benchmark,
                "metric": metric,
                "value": None if value is None or pd.isna(value) else float(value),
            },
        )

    def save_outputs(self) -> None:
        self.context["output_dir"].mkdir(parents=True, exist_ok=True)
        self.atomic_parquet(self.context["daily"], self.context["daily_path"])
        self.atomic_csv(self.context["overall"], self.context["overall_path"])
        self.atomic_csv(self.context["yearly"], self.context["yearly_path"])
        self.atomic_csv(self.context["quarterly"], self.context["quarterly_path"])

    def plot_report(self) -> None:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.ticker import PercentFormatter

        daily: pd.DataFrame = self.context["daily"]
        dates = pd.to_datetime(daily["trade_date"], format="%Y%m%d")
        descriptor, temporary = tempfile.mkstemp(dir=self.context["output_dir"], suffix=".pdf")
        os.close(descriptor)
        try:
            with PdfPages(temporary) as pdf:
                figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
                for top_n in self.context["top_ns"]:
                    axis.plot(dates, daily[f"top{top_n}_gross_return"].cumsum(), label=f"Top {top_n}", linewidth=1)
                axis.plot(
                    dates,
                    daily["benchmark_universe"].cumsum(),
                    label="Baseline",
                    color="black",
                    linestyle="--",
                )
                axis.set_title("Daily Model Arithmetic Cumulative Return (%)")
                axis.set_ylabel("Arithmetic cumulative return")
                axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
                axis.grid(alpha=0.3)
                axis.legend(loc="upper left", ncol=3)
                self.format_date_axis(axis, mdates)
                pdf.savefig(figure)
                plt.close(figure)

                figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
                for top_n in self.context["top_ns"]:
                    axis.plot(dates, daily[f"top{top_n}_net_value"] - 1.0, label=f"Top {top_n}", linewidth=1)
                axis.set_title(f"Compounded Return After Costs ({self.config.transaction_cost_rate:.2%})")
                axis.set_ylabel("Compounded net return")
                axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
                axis.grid(alpha=0.3)
                axis.legend(loc="upper left", ncol=3)
                self.format_date_axis(axis, mdates)
                pdf.savefig(figure)
                plt.close(figure)

                summary_top_n = 5 if 5 in self.context["top_ns"] else self.context["top_ns"][0]
                figure, axis = plt.subplots(figsize=(14, 6), constrained_layout=True)
                self.draw_quarterly_performance(axis, daily, summary_top_n)
                pdf.savefig(figure)
                plt.close(figure)

                rank_ic_mean = float(daily["rank_ic"].mean())
                figure, axis = plt.subplots(figsize=(12, 4), constrained_layout=True)
                axis.bar(dates, daily["rank_ic"], width=1, alpha=0.3, label="Daily RankIC")
                axis.plot(
                    dates,
                    daily["rank_ic"].rolling(20, min_periods=1).mean(),
                    color="red",
                    label="20-day rolling mean",
                )
                axis.axhline(
                    rank_ic_mean,
                    color="black",
                    linestyle="--",
                    linewidth=1,
                    label=f"Overall mean = {rank_ic_mean:.4f}",
                )
                axis.set_title("Daily RankIC and Means")
                axis.grid(alpha=0.3)
                axis.legend(loc="upper left")
                self.format_date_axis(axis, mdates)
                pdf.savefig(figure)
                plt.close(figure)
            os.replace(temporary, self.context["report_path"])
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def format_date_axis(axis: Any, mdates: Any) -> None:
        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    def draw_quarterly_performance(self, axis: Any, daily: pd.DataFrame, top_n: int) -> None:
        from matplotlib.ticker import PercentFormatter

        dated = daily.assign(
            quarter=pd.PeriodIndex(pd.to_datetime(daily["trade_date"], format="%Y%m%d"), freq="Q").astype(str),
        )
        rows = []
        for period, frame in dated.groupby("quarter", sort=True):
            rows.append(self.quarterly_plot_row(str(period), frame, top_n))
        rows.append(self.quarterly_plot_row("Overall", daily, top_n))
        summary = pd.DataFrame(rows)
        positions = np.arange(len(summary), dtype=float)
        positions[-1] += 0.7
        width = 0.34
        axis.bar(positions - width / 2, summary["return"], width=width, label="Arithmetic cumulative return")
        axis.bar(positions + width / 2, summary["max_drawdown"], width=width, label="Max drawdown")
        axis.set_xticks(positions, summary["period"], rotation=45, ha="right")
        axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
        axis.set_ylabel("Return / drawdown")
        axis.grid(axis="y", alpha=0.3)
        ratio_axis = axis.twinx()
        ratio_axis.plot(positions, summary["information_ratio"], color="green", marker="o", label="Information ratio")
        ratio_axis.set_ylabel("Annualized information ratio")
        handles, labels = axis.get_legend_handles_labels()
        other_handles, other_labels = ratio_axis.get_legend_handles_labels()
        axis.legend(handles + other_handles, labels + other_labels, loc="upper left", ncol=3)
        axis.set_title(f"Top {top_n} Quarterly Performance and Overall Summary")

    def quarterly_plot_row(self, period: str, frame: pd.DataFrame, top_n: int) -> dict[str, Any]:
        returns = frame[f"top{top_n}_gross_return"]
        return {
            "period": period,
            "return": float(returns.sum()),
            "max_drawdown": self.arithmetic_max_drawdown(returns),
            "information_ratio": self.information_ratio(returns, frame["benchmark_universe"]),
        }

    def save_metadata(self) -> None:
        metadata = {
            "version": 3,
            "flow": "ranking_backtest",
            "input_file": str(self.context["input_file"]),
            "input_sha256": self.file_sha256(self.context["input_file"]),
            "input_rows": len(self.context["frame"]),
            "return_unit": "decimal",
            "source_return_unit": self.config.return_unit,
            "return_horizon": self.config.return_horizon,
            "top_ns": self.context["top_ns"],
            "transaction_cost_rate": self.config.transaction_cost_rate,
            "annual_risk_free_rate": self.config.annual_risk_free_rate,
            "annualization_days": self.config.annualization_days,
            "minimum_index_weight_coverage": self.config.minimum_index_weight_coverage,
            "index_weight_columns": self.context["index_columns"],
            "artifacts": {
                "daily": "daily.parquet",
                "overall": "overall.csv",
                "yearly": "yearly.csv",
                "quarterly": "quarterly.csv",
                "report": "backtest.pdf" if self.config.plot_report else None,
            },
            "definitions": {
                "ic": "daily Pearson correlation of pred and actual_return over valid model candidates",
                "rank_ic": "daily Spearman correlation of pred and actual_return over valid model candidates",
                "icir": "period mean daily IC divided by sample standard deviation; not annualized",
                "sharpe": "annualized daily excess return over configured annual risk-free rate",
                "information_ratio": "annualized active return divided by sample tracking error",
                "index_return": "sum(weight * actual_return) / covered weight when coverage meets the threshold",
                "index_weight_coverage": "sum of weights with a valid realized return, capped at one",
                "turnover": "half L1 distance between consecutive equal-weight target portfolios",
                "gross_cumulative_return": "arithmetic sum of daily gross returns",
                "net_cumulative_return": "compound daily gross return minus turnover cost; initial cost is zero",
            },
        }
        self.atomic_text(self.context["metadata_path"], json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")

    def publish_output(self) -> None:
        self.context.update(
            status="done",
            output_dir=self.context["output_dir"],
            daily_file=self.context["daily_path"],
            overall_file=self.context["overall_path"],
            yearly_file=self.context["yearly_path"],
            quarterly_file=self.context["quarterly_path"],
            report_file=self.context["report_path"] if self.config.plot_report else None,
            metadata_file=self.context["metadata_path"],
        )

    @staticmethod
    def safe_correlation(left: pd.Series, right: pd.Series, *, method: str) -> float:
        if len(left) < 2 or left.nunique() < 2 or right.nunique() < 2:
            return 0.0
        value = left.corr(right, method=method)
        return 0.0 if pd.isna(value) or not np.isfinite(value) else float(value)

    @staticmethod
    def portfolio_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
        return 0.5 * sum(
            abs(current.get(code, 0.0) - previous.get(code, 0.0)) for code in previous.keys() | current.keys()
        )

    @staticmethod
    def ratio(values: pd.Series) -> float:
        values = values.dropna()
        deviation = values.std(ddof=1)
        if len(values) < 2 or pd.isna(deviation) or np.isclose(deviation, 0.0):
            return 0.0
        return float(values.mean() / deviation)

    def sharpe(self, returns: pd.Series) -> float:
        daily_risk_free = (1.0 + self.config.annual_risk_free_rate) ** (1.0 / self.config.annualization_days) - 1.0
        return self.annualized_ratio(returns - daily_risk_free)

    def information_ratio(self, returns: pd.Series, benchmark: pd.Series) -> float:
        aligned = pd.concat((returns, benchmark), axis=1).dropna()
        return self.annualized_ratio(aligned.iloc[:, 0] - aligned.iloc[:, 1]) if not aligned.empty else 0.0

    def annualized_ratio(self, values: pd.Series) -> float:
        return self.ratio(values) * math.sqrt(self.config.annualization_days)

    def annualized_volatility(self, values: pd.Series) -> float:
        deviation = values.dropna().std(ddof=1)
        return (
            0.0
            if pd.isna(deviation) or not np.isfinite(deviation)
            else float(deviation * math.sqrt(self.config.annualization_days))
        )

    @staticmethod
    def compounded_return(returns: pd.Series) -> float:
        values = returns.dropna().to_numpy(dtype=float)
        return float(np.prod(1.0 + values) - 1.0) if len(values) else 0.0

    @staticmethod
    def max_drawdown(returns: pd.Series) -> float:
        values = returns.dropna().to_numpy(dtype=float)
        if values.size == 0:
            return 0.0
        net_values = np.concatenate(([1.0], np.cumprod(1.0 + values)))
        return float(np.min(net_values / np.maximum.accumulate(net_values) - 1.0))

    @staticmethod
    def arithmetic_max_drawdown(returns: pd.Series) -> float:
        values = returns.dropna().to_numpy(dtype=float)
        if values.size == 0:
            return 0.0
        cumulative = np.concatenate(([0.0], np.cumsum(values)))
        return float(np.min(cumulative - np.maximum.accumulate(cumulative)))

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".csv", text=True)
        os.close(descriptor)
        try:
            frame.to_csv(temporary, index=False)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".parquet")
        os.close(descriptor)
        try:
            frame.to_parquet(temporary, index=False, compression="zstd")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def atomic_text(path: Path, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=path.suffix, text=True)
        os.close(descriptor)
        try:
            Path(temporary).write_text(content, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
