"""Alpha158 signal-time universe selection."""

import polars as pl

from axonx.task.builtins.stock.data import KEYS
from axonx.task.builtins.stock.portfolio import BaseStockPortfolioTask
from axonx.task.models.reports import PortfolioUniverse


class Alpha158PortfolioTask(BaseStockPortfolioTask):
    def build_universes(self):
        yield PortfolioUniverse(key="all", label="全市场", parameters={"kind": "all"})
        yield PortfolioUniverse(key="hs300", label="沪深300", parameters={"kind": "index", "index_codes": ["hs300"]})

    def select_universe(self, signals, universe):
        if universe.key == "hs300":
            signals = signals.filter(pl.col("index_weight_hs300") > 0)
        return signals.select(*KEYS)
