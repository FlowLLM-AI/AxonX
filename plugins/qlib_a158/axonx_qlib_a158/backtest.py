"""Alpha158 execution reports on the shared stock ledger."""

from axonx.task.builtins.stock.backtest import BaseStockBacktestTask

from .internal.reference import DEVIATIONS, QLIB_REFERENCE


class Alpha158BacktestTask(BaseStockBacktestTask):
    def calculate(self):
        if self.input_params.as_of_date is None:
            self.input_params.as_of_date = self.plan.predictions["trade_date"].max()
        super().calculate()

    def build_output_params(self):
        output = super().build_output_params()
        output.protocol.update(
            qlib_reference=QLIB_REFERENCE,
            qlib_deviations={key: DEVIATIONS[key] for key in ("execution", "limits", "strategy", "evaluation")},
        )
        return output
