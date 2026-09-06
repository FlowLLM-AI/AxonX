"""All dataframe work stays inside one independent task process."""

import os
from pathlib import Path
from axonx.task import BaseTask, BaseConfig


class SalesConfig(BaseConfig):
    """Configure optional CSV input and required Parquet output paths."""

    output: str
    input: str | None = None


class SalesTask(BaseTask):
    """Aggregate synthetic or CSV sales data and write a Parquet result."""

    config: SalesConfig
    output_keys = ("output", "rows", "revenue", "pid")

    def build_task_steps(self):
        """Yield data loading, aggregation, and persistence steps."""
        yield self.load
        yield self.aggregate
        yield self.save

    def load(self):
        """Load input lazily or create the built-in demonstration data."""
        import polars as pl

        self.context["frame"] = (
            pl.scan_csv(self.config.input)
            if self.config.input
            else pl.DataFrame(
                {
                    "product": ["A", "B", "A"],
                    "quantity": [2, 3, 1],
                    "price": [10.0, 15.0, 10.0],
                },
            ).lazy()
        )

    def aggregate(self):
        """Compute revenue totals grouped by product."""
        import polars as pl

        self.context["result"] = (
            self.context["frame"]
            .with_columns((pl.col("quantity") * pl.col("price")).alias("revenue"))
            .group_by("product")
            .agg(pl.col("revenue").sum())
            .sort("product")
            .collect()
        )

    def save(self):
        """Write Parquet output and publish summary metadata."""
        path = Path(self.config.output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self.context["result"]
        result.write_parquet(path)
        self.context.update(
            output=str(path),
            rows=result.height,
            revenue=result["revenue"].sum(),
            pid=os.getpid(),
        )
