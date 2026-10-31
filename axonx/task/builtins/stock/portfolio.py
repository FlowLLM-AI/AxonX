"""Signal-time portfolio construction and reusable position decision rules."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

import polars as pl
from pydantic import Field, model_validator

from ...core.research import BasePortfolioTask
from ...models.artifacts import PredictionProtocol, task_protocol
from ...models.base import TaskModel
from ...models.identity import TaskType, task_type_from_id
from ...models.reports import PortfolioDefinition, PortfolioUniverse
from ...storage.artifacts import artifact_record
from ...storage.files import atomic_write, file_revision
from ...storage.inputs import read_upstream_metadata, upstream_artifacts, upstream_input_artifact
from .data import KEYS, normalize_keys, validate_keys
from .models import StockPortfolioInput, StockPortfolioOutput
from .protocol import STOCK_SIGNALS_FORMAT


class StockStrategy(TaskModel):
    """Shared fixed-expiry and rank-retention semantics, independent of execution costs."""

    kind: str = "fixed_expiry"
    holding_days: int | None = Field(default=1, ge=1)
    minimum_holding_days: int = Field(default=1, ge=0)
    replacement_fraction: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    rank_buffer: float = Field(default=1.0, ge=1, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def strategy_defaults(cls, value):
        value = dict(value)
        value.setdefault("holding_days", None if value.get("kind") == "rank_retention" else 1)
        return value

    @model_validator(mode="after")
    def validate_strategy(self):
        if self.kind == "fixed_expiry":
            if self.holding_days is None:
                raise ValueError("Fixed expiry requires holding_days")
        elif self.kind == "rank_retention":
            if self.holding_days is not None:
                raise ValueError("Rank retention requires holding_days=None")
        else:
            raise ValueError(f"Unknown stock strategy: {self.kind}")
        return self

    def definition(self) -> dict:
        if self.kind == "fixed_expiry":
            return self.model_dump(include={"kind", "holding_days"})
        return self.model_dump(exclude={"holding_days"})

    def policy(self):
        if self.kind == "fixed_expiry":
            return None
        return RankRetentionPolicy(self.replacement_fraction, self.minimum_holding_days, self.rank_buffer)


@dataclass(frozen=True)
class RankRetentionPolicy:
    replacement_fraction: float = 1.0
    minimum_holding_days: int = 1
    rank_buffer: float = 1.0

    def replacement_limit(self, n: int) -> int:
        return max(1, math.floor(n * self.replacement_fraction + 1e-12))

    def should_exit(self, *, rank: int | None, age: int, n: int) -> bool:
        return age >= self.minimum_holding_days and (rank is None or rank > math.ceil(n * self.rank_buffer))


def rank_signals(signals: pl.DataFrame) -> pl.DataFrame:
    """Rank final scores once, before universe-specific eligibility is applied."""
    return signals.sort(
        ["trade_date", "trade_time", "pred", "ts_code"], descending=[False, False, True, False]
    ).with_columns(
        pl.int_range(1, pl.len() + 1).over(list(KEYS[:2])).alias("rank"),
        pl.when(pl.col("is_buyable_at_signal"))
        .then(pl.col("is_buyable_at_signal").cast(pl.Int64).cum_sum().over(list(KEYS[:2])))
        .otherwise(None)
        .alias("buyable_rank"),
    )


def restore_portfolio_signals(predictions, rankings, *, score_column, scores=None):
    """Join only published deltas; never recompute a frozen score or candidate rank."""
    predictions, rankings = normalize_keys(predictions), normalize_keys(rankings)
    validate_keys(predictions)
    validate_keys(rankings)
    if rankings.join(predictions.select(*KEYS), on=list(KEYS), how="anti").height:
        raise ValueError("Rankings must be a subset of prediction keys")
    if scores is not None:
        scores = normalize_keys(scores)
        validate_keys(scores)
        if (
            scores.height != predictions.height
            or predictions.select(*KEYS).join(scores.select(*KEYS), on=list(KEYS), how="anti").height
        ):
            raise ValueError("Scores must cover prediction keys exactly")
        predictions = predictions.drop("pred", strict=False).join(scores, on=list(KEYS), validate="1:1")
    else:
        predictions = predictions.with_columns(pl.col(score_column).alias("pred"))
    signals = rank_signals(predictions)
    return signals.join(rankings, on=list(KEYS), how="left", validate="1:1", maintain_order="left").with_columns(
        pl.col("target_rank").is_not_null().alias("is_portfolio_candidate")
    )


def prepare_portfolio_signals(signals: pl.DataFrame, universe_keys: pl.DataFrame | None = None) -> pl.DataFrame:
    """Freeze signal-time eligibility and deterministic ranks without consulting labels or execution quotes."""
    signals = normalize_keys(signals)
    validate_keys(signals)
    candidates = signals.filter(pl.col("is_model_candidate") & pl.col("is_buyable_at_signal"))
    if universe_keys is not None:
        keys = normalize_keys(universe_keys.select(*KEYS))
        validate_keys(keys)
        if keys.join(signals.select(*KEYS), on=list(KEYS), how="anti").height:
            raise ValueError("Universe keys must be a subset of prediction keys")
        candidates = candidates.join(keys, on=list(KEYS), how="semi")
    candidates = candidates.sort(
        ["trade_date", "trade_time", "pred", "ts_code"], descending=[False, False, True, False]
    ).with_columns(pl.int_range(1, pl.len() + 1).over(list(KEYS[:2])).alias("target_rank"))
    return signals.join(
        candidates.select(*KEYS, "target_rank"), on=list(KEYS), how="left", validate="1:1"
    ).with_columns(pl.col("target_rank").is_not_null().alias("is_portfolio_candidate"))


class PortfolioReader:
    """Resolve one portfolio publication and share its source data across all plans."""

    def __init__(self, task, task_id):
        _, metadata = read_upstream_metadata(task.workspace_path, task_id)
        self.output = StockPortfolioOutput.model_validate(metadata["output_params"])
        params = metadata["input_params"]
        if params.get("input_file") is not None:
            path = task.resolve_workspace_path(params["input_file"])
            if file_revision(path) != self.output.protocol["input_revisions"]["predictions"]:
                raise ValueError("Predictions changed since portfolio construction")
        else:
            source = next(t for t in params["upstream_task_ids"] if task_type_from_id(t) == TaskType.PREDICT)
            path = upstream_input_artifact(task, metadata, source, "predictions")
        names = tuple(self.output.artifacts)
        self.paths = dict(zip(names, upstream_artifacts(task, task_id, *names, metadata=metadata), strict=True))
        self.paths["predictions"] = path
        self.predictions = pl.read_parquet(path)
        self.rankings = pl.read_parquet(self.paths["rankings"])
        self.scores = pl.read_parquet(self.paths["scores"]) if "scores" in self.paths else None
        self._signals = {}

    def signals(self, portfolio):
        universe = next(
            u for u in self.output.universes if (u.parameters or {"kind": u.key}) == portfolio.portfolio_id["universe"]
        )
        if universe.key not in self._signals:
            self._signals[universe.key] = restore_portfolio_signals(
                self.predictions,
                self.rankings.filter(pl.col("universe_key") == universe.key).drop("universe_key"),
                score_column=self.output.score_column,
                scores=self.scores,
            )
        return self._signals[universe.key]


def portfolio_targets(signals: pl.DataFrame, n: int) -> pl.DataFrame:
    return signals.filter(pl.col("is_portfolio_candidate") & (pl.col("target_rank") <= n)).with_columns(
        pl.lit(1.0 / n).alias("target_weight")
    )


def portfolio_identity(*, universe, score_selection, strategy, top_n, trade_time):
    return {
        "universe": universe,
        "score_selection": score_selection,
        "strategy": strategy,
        "top_n": top_n,
        "allocation": "equal_slot",
        "trade_time": trade_time,
    }


class BaseStockPortfolioTask(BasePortfolioTask):
    input_cls = StockPortfolioInput
    output_cls = StockPortfolioOutput
    input_params: StockPortfolioInput
    source_protocol: dict
    score_columns: dict[str, str] | None

    def build_task_steps(self):
        yield self.resolve_inputs
        yield self.calculate

    def resolve_inputs(self):
        p = self.input_params
        self.source_protocol = {}
        if p.input_file is None:
            if p.score_columns is not None:
                raise ValueError(
                    "score_columns is only for an explicit input_file; source Tasks declare their own members"
                )
            source = p.upstream_task_id(TaskType.PREDICT)
            _, metadata = read_upstream_metadata(self.workspace_path, source)
            (path,) = upstream_artifacts(self, source, "predictions", metadata=metadata)
            self.source_protocol = metadata["output_params"]["protocol"]
            PredictionProtocol.model_validate(self.source_protocol)
        else:
            path = self.resolve_workspace_path(p.input_file)
        self.score_columns = self.source_protocol.get("score_columns", p.score_columns)
        self.state["input_path"] = path
        self.state["input_revision"] = file_revision(path)
        self.state["signals"] = pl.read_parquet(path)

    def prepare_signals(self):
        self.state["score_selection"] = {"method": "model"}
        self.state["score_column"] = "pred"
        self.state["signals"] = rank_signals(self.state["signals"])

    def build_universes(self) -> Iterable[PortfolioUniverse]:
        yield PortfolioUniverse(key="all", label="All market", parameters={"kind": "all"})

    def select_universe(self, signals, universe):  # pylint: disable=unused-argument
        return signals.select(*KEYS)

    def strategy(self) -> StockStrategy:
        return StockStrategy(holding_days=self.input_params.holding_days)

    def calculate(self):
        self.prepare_signals()
        self.state.update(portfolios=[], artifacts={})
        universes = list(self.build_universes())
        if not universes or len({u.key for u in universes}) != len(universes):
            raise ValueError("Universe keys must be nonempty and unique")
        signals = self.state["signals"]
        if signals.is_empty() or signals["trade_time"].n_unique() != 1:
            raise ValueError("Each portfolio requires nonempty signals at one trade time")
        strategies = (
            [StockStrategy.model_validate(value) for value in self.input_params.strategies]
            if self.input_params.strategies is not None
            else [self.strategy()]
        )
        definitions = [item.definition() for item in strategies]
        if any(value in definitions[:index] for index, value in enumerate(definitions)):
            raise ValueError("Portfolio strategies must be distinct")
        self.state["universes"] = universes
        artifacts = {"rankings": "rankings"}
        if self.state["score_column"] is None:
            artifacts["scores"] = self.save_frame("scores", signals.select(*KEYS, "pred"))
        rankings = []
        for universe in universes:
            prepared = prepare_portfolio_signals(signals, self.select_universe(signals, universe))
            rankings.append(
                prepared.filter(pl.col("is_portfolio_candidate")).select(
                    pl.lit(universe.key).alias("universe_key"), *KEYS, "target_rank"
                )
            )
            for strategy in definitions:
                for n in self.input_params.top_ns:
                    self.state["portfolios"].append(
                        PortfolioDefinition(
                            portfolio_id=portfolio_identity(
                                universe=universe.parameters or {"kind": universe.key},
                                score_selection=self.state["score_selection"],
                                strategy=strategy,
                                top_n=n,
                                trade_time=str(signals["trade_time"][0]),
                            ),
                            artifacts=artifacts,
                        )
                    )
        self.save_frame("rankings", pl.concat(rankings))
        if file_revision(self.state["input_path"]) != self.state["input_revision"]:
            raise ValueError("Predictions changed during portfolio construction")

    def save_frame(self, key, frame):
        path = self.task_dir / f"{key}.parquet"
        atomic_write(path, lambda temporary: frame.write_parquet(temporary, compression="zstd"))
        self.state["artifacts"][key] = artifact_record(path, self.task_dir)
        return key

    def build_output_params(self):
        source = (
            {"input_revisions": {"predictions": self.state["input_revision"]}}
            if self.input_params.input_file is not None
            else {}
        )
        return self.output_cls(
            signals_format=STOCK_SIGNALS_FORMAT,
            score_column=self.state["score_column"] or "pred",
            universes=self.state["universes"],
            portfolios=self.state["portfolios"],
            artifacts=self.state["artifacts"],
            protocol=task_protocol(
                TaskType.PORTFOLIO,
                market_upstream_task_id=self.source_protocol.get("market_upstream_task_id"),
                allocation="New entries at most 1/N equity; retained weights drift; unfilled slots retain cash",
                **source,
            ),
        )
