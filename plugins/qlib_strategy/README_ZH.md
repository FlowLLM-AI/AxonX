# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 继承 `qlib_factor` 和 `qlib_a158`，在同一预测上研究持仓策略。框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。不提供固定到期参数，`planned_exit_date` 为空。

插件版本 0.3.0 要求 Python 3.12+、AxonX `>=0.3.0` 和上游研究插件 `>=0.3.0`。按依赖顺序安装，研究产物使用协议 v1。

## 安装与执行

研究插件尚未发布到 PyPI。先克隆仓库并从根目录安装 AxonX 0.3.0 主包（`pip install -e .`），以下命令从仓库根目录执行。本机 Agent 开发按依赖顺序安装到执行服务的 Python 环境：

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
axonx plugin install -e plugins/qlib_strategy
```

新的 `exec` 进程加载当前 Python 源码；依赖或入口点变化后重新安装，重启常驻服务以刷新 Task 目录、Schema 和已加载依赖。固定版本实验去掉 `-e`。远程部署使用普通安装，在同一目标服务按顺序安装上游插件；先配置 `AXONX_TARGET_TOKEN`，并替换以下示例地址：

```bash
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_factor --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_strategy --output /tmp/axonx-wheels
# 将实际 wheel 逐一上传至 POST /upload，再按上方依赖顺序安装。
axonx plugin install '<qlib_a158 upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_factor upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_strategy upload.location>' --target http://research.example:1024 --client-timeout 600
axonx exec --task qlib_strategy_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

可复用成功的基础或增强预测。从执行日志或 `status --detail full` 保存 Task ID 和 `started_at`，成功后再读取结果。上游 `qlib_strategy_etl`、`qlib_strategy_analysis`、`qlib_strategy_train`、`qlib_strategy_predict` 注册因子层实现；策略比较直接复用已有预测。安装修改所选解释器；新 CLI 进程发现已安装插件，定义查询和 Studio 则保留服务启动时的目录，直到重启。安装或核验失败时停止并报告。

每次安装后，使用返回的工作区相对 `path` 清理上传暂存文件。远程源码路径属于目标机器。所有层安装完成后重启常驻服务并核验定义；完整流程见[上传、核验与清理](../../docs/zh/plugins/management.md#部署到远程)。

## 执行与配置

`exec` 在新的本地 CLI 进程中同步执行；`--target` 将命令转发到目标服务的 CLI 子进程，命令返回 Task 退出码。执行配置优先级为 CLI 参数 → 服务 `get_config` → 内置默认值。通过 `--workspace-dir /absolute/path` 为行情和上游 Task 选择一致的工作区。定义和状态 Job 需要运行中的服务。同名重跑替换产物，应同时记录 Task ID 和 `started_at`；展示副本不能作为研究输入。

策略层仅贡献 Task 注册，没有独立应用预设。使用标准 `axonx app` 配置或 `--config qlib_factor`。策略参数属于 `qlib_strategy_backtest`，其余上游注册复用因子/基础层实现。预测可指定一个 Train 和一个可选兼容 ETL，用已有模型预测新数据。

## 本地验证

在仓库根目录安装全部三个研究插件及开发依赖后执行：

```bash
python -m pytest plugins/qlib_strategy/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

研究测试使用临时合成行情执行因子和策略链路，覆盖产物交换和显式选择预测 ETL。

## 实验记录

实验设置、完整结果与产物来源统一见[研究实验指南](../../docs/zh/research/alpha158-case.md)。三组配置已在 45 机器使用买入 0.05%、卖出 0.15% 的费用重新运行。

AxonX 在 `axonx.task.models.artifacts` 定义协议 v1，使用 `TaskType` 作为 `task_type`，产物记录包含任务相对 `path`、`size` 和 `revision`。版本使用 `size:mtime_ns`，表示文件版本，不是内容校验和。训练发布 `output_params.protocol` 和 `models.json` 模型集合。预测通过 `axonx.task.storage.inputs` 快照模型成员并固定上游产物。特征语义与指纹属于 `axonx_qlib_a158.internal.protocol`；训练、分析和预测在消费数据前校验该契约。预测发布 `model_identity`、`dates`、`score_columns` 和文件版本。读取端校验协议头与特征语义。

一次回测 Task 同时发布**全市场**（`all`）与**沪深300**（`hs300`）两个独立报告。Studio 通过下拉框切换股池，策略比较两侧可独立选择。信号时点 `index_weight_hs300 > 0` 定义沪深300成分。回测输出使用 `default_universe`、`universes` 和统一产物表。
