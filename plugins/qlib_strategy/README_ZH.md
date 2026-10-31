# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 扩展 `qlib_a158`，在固定的历史预测上开展离线持仓策略研究。回测框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。`rank_buffer` 必须为有限值。不提供固定到期参数，`planned_exit_date` 为空。

插件版本 0.3.0 要求 Python 3.12+、AxonX `>=0.3.1` 和上游研究插件 `>=0.3.0`。按依赖顺序安装，研究产物使用协议 v1。

## 安装与执行

研究插件尚未发布到 PyPI。先克隆仓库并从根目录安装 AxonX 0.3.1 主包（`pip install -e .`），以下命令从仓库根目录执行。本机 Agent 开发按依赖顺序安装到执行服务的 Python 环境：

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_strategy
```

远程安装与服务刷新见[插件管理](../../docs/zh/plugins/management.md)。以下示例需准备插件、数据与 `AXONX_TARGET_TOKEN`，并将 `http://research.example:1024` 替换为实际服务地址。

```bash
axonx exec --task qlib_strategy_portfolio --upstream-task-ids '["<predict_task_id>"]' --top-ns '[20,30]' --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 --target http://research.example:1024
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<portfolio_task_id>"]' --as-of-date 20261008 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

可复用成功的基础或增强预测。从执行日志或 `status --detail full` 保存 Task ID 和 `started_at`，成功后再读取结果。本插件仅注册 `qlib_strategy_portfolio`，策略比较复用已有基础或增强预测。安装修改所选解释器；新 CLI 进程发现已安装插件，定义查询和 Studio 则保留服务启动时的目录，直到重启。安装或核验失败时停止并报告。

## 执行与配置

使用标准 `axonx app` 配置。本插件仅注册 `qlib_strategy_portfolio`，依赖 `qlib_a158`；`qlib_factor` 为可选依赖。使用基础或增强训练任务及 `qlib_a158_predict` 生成预测；预测可指定一个 Train 和一个可选兼容 ETL，用已有模型预测新数据。

## 本地验证

在仓库根目录安装全部三个研究插件及开发依赖后执行：

```bash
python -m pytest plugins/qlib_strategy/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

研究测试使用临时合成行情执行因子和策略链路，覆盖产物交换和显式选择预测 ETL。

## 实验记录

共享设定、结果、复现命令和 Task 来源统一维护在 [Alpha158 改进实验](../../docs/zh/research/alpha158-case.md)。产物字段与股票池报告遵循[共享协议](../../docs/zh/reference/research-artifacts.md)。
