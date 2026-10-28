# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 为 Alpha158 ETL 增加 13 个可选的市场矩、中性动量和风险特征，共输出 171 个特征列。训练按组选择，默认 `none` 使用 158 个基础特征。下方示例选择 `risk`，共 160 个特征。

训练继承基础插件的截止日隔离、末尾 10% 日期早停与全训练期重拟合。预测和普通回测复用基础插件。

## 因子与时点

| 分组     | 特征数 | 定义                                         |
| -------- | -----: | -------------------------------------------- |
| mean     |      4 | 各窗口收益截面缩尾均值，反映市场整体涨跌方向 |
| variance |      4 | 各窗口收益截面缩尾样本方差，反映股票涨跌分歧 |
| neutral  |      3 | 5/10/20 日 beta 调整动量                     |
| risk     |      2 | 20 日特质波动与下行风险                      |

每只股票收益为复权 C(T)/C(T−h)−1，h=1/3/5/10 个市场交易日。两个端点须有报价且成交量、成交额和复权价格为正；包含涨跌停股票，不使用未来标签或可交易性筛选。各日期、各窗口独立用 2%/98% 线性分位缩尾，再计算等权均值与样本方差（ddof=1）。空股票池保留缺失，单股票方差缺失。方差描述截面分歧；均值接近零并不能单独证明多数股票震荡。

全局矩在 T 收盘后可用，同日所有股票共享相同值；动量/风险因子随股票变化。全局矩不能用单因子截面 IC 判断，应比较模型消融。定义见 [cross_section.py](axonx_qlib_factor/internal/cross_section.py)；ETL 保存各窗口样本数和每日因子值。

`context_groups` 接受逗号分隔的 `mean`、`variance`、`neutral`、`risk`，或 `none`。默认仍为 `none`；本文因子版显式使用 `risk`。不支持的组名和上下文特征列会在校验时报错。

`context_windows` 可选择 `[1,3,5,10]` 的非空子集，默认全部四个窗口。ETL 发布全部 13 列，context_windows 只过滤全局均值/方差；个股组使用固定窗口。消融复用同一数据集，训练协议记录实际窗口。例如 `--context-groups mean,variance --context-windows '[10]'` 只加入两个 10 日因子。

Beta 使用 T−1 及之前 60 个市场日，至少需要 30 个股票与市场配对收益。股票日收益按当日 2%/98% 分位缩尾，市场收益为其等权均值。Beta 为协方差除以市场方差，并限制在 [−3,3]；方差 ≤1e−12 时保持空值。中性动量为股票 5/10/20 日累计收益减去历史 beta × 市场累计收益。残差波动为“股票日收益 − 历史 beta × 市场日收益”的 20 日样本标准差；下行风险为 sqrt(mean(min(股票日收益,0)²))。风险窗口至少需要 20 日内 16 个有效观测；当日行情无效时所有股票特征保持空值。

插件版本 0.3.0 要求 Python 3.12+、AxonX `>=0.3.0` 和上游研究插件 `>=0.3.0`。按依赖顺序安装，研究产物使用协议 v1。

## 安装与执行

研究插件尚未发布到 PyPI。先克隆仓库并从根目录安装 AxonX 0.3.0 主包（`pip install -e .`），以下命令从仓库根目录执行。本机 Agent 开发按依赖顺序安装到执行服务的 Python 环境：

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
```

新的 `exec` 进程加载当前 Python 源码；依赖或入口点变化后重新安装，重启常驻服务以刷新 Task 目录、Schema 和已加载依赖。固定版本实验去掉 `-e`。远程部署使用普通安装，在同一目标服务按顺序安装上游插件；先配置 `AXONX_TARGET_TOKEN`，并替换以下示例地址：

```bash
axonx plugin build ./plugins/qlib_a158 --output /tmp/axonx-wheels
axonx plugin build ./plugins/qlib_factor --output /tmp/axonx-wheels
# 将实际 wheel 逐一上传至 POST /upload，再按上方依赖顺序安装。
axonx plugin install '<qlib_a158 upload.location>' --target http://research.example:1024 --client-timeout 600
axonx plugin install '<qlib_factor upload.location>' --target http://research.example:1024 --client-timeout 600
axonx get_task_def --task qlib_factor_train --target http://research.example:1024

axonx exec --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups risk --feature-fraction 1.0 --target http://research.example:1024
axonx exec --task qlib_factor_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_backtest --upstream-task-ids '["<predict_task_id>"]' \
  --top-ns '[5,10,20,30]' --as-of-date 20261008 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

从执行日志或 `status --detail full` 保存 Task ID 和 `started_at`；仅在退出码为零且状态为 `succeeded` 后提交下游。`qlib_factor_analysis` 是可选的因子分析分支。安装修改所选解释器；新 CLI 进程发现已安装插件，定义查询和 Studio 则保留服务启动时的目录，直到重启。安装或核验失败时停止并报告。[Qlib Alpha158](../qlib_a158/README_ZH.md)

每次安装后，使用返回的工作区相对 `path` 清理上传暂存文件。远程源码路径属于目标机器。所有层安装完成后重启常驻服务并核验定义；完整流程见[上传、核验与清理](../../docs/zh/plugins/management.md#部署到远程)。

## 执行与配置

`exec` 在新的本地 CLI 进程中同步执行；`--target` 将命令转发到目标服务的 CLI 子进程，命令返回 Task 退出码。执行配置优先级为 CLI 参数 → 服务 `get_config` → 内置默认值。通过 `--workspace-dir /absolute/path` 为行情和上游 Task 选择一致的工作区。定义和状态 Job 需要运行中的服务。同名重跑替换产物，应同时记录 Task ID 和 `started_at`；展示副本不能作为研究输入。

可通过 `axonx app --config qlib_factor` 启动继承的应用配置；YAML 仅包含 `extends: default`，已安装插件的 `plugin.yaml` 贡献 Task 注册。日期、特征组和模型参数在每次执行时传入。可用注册为 `qlib_factor_etl`、`qlib_factor_analysis`、`qlib_factor_train`、`qlib_factor_predict` 和 `qlib_factor_backtest`。预测可指定一个 Train 和一个可选兼容 ETL，用已有模型预测新数据。

## 本地验证

在仓库根目录安装全部三个研究插件及开发依赖后执行：

```bash
python -m pytest plugins/qlib_factor/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

研究测试使用临时合成行情执行因子和策略链路，覆盖产物交换和显式选择预测 ETL。

## 实验记录

实验设置、完整结果与产物来源统一见[研究实验指南](../../docs/zh/research/alpha158-case.md)。三组配置已在 45 机器使用买入 0.05%、卖出 0.15% 的费用重新运行。

AxonX 在 `axonx.task.models.artifacts` 定义协议 v1，使用 `TaskType` 作为 `task_type`，产物记录包含任务相对 `path`、`size` 和 `revision`。版本使用 `size:mtime_ns`，表示文件版本，不是内容校验和。训练发布 `output_params.protocol` 和 `models.json` 模型集合。预测通过 `axonx.task.storage.inputs` 快照模型成员并固定上游产物。特征语义与指纹属于 `axonx_qlib_a158.internal.protocol`；训练、分析和预测在消费数据前校验该契约。预测发布 `model_identity`、`dates`、`score_columns` 和文件版本。读取端校验协议头与特征语义。

一次回测 Task 同时发布**全市场**（`all`）与**沪深300**（`hs300`）两个独立报告。Studio 通过下拉框切换股池，策略比较两侧可独立选择。信号时点 `index_weight_hs300 > 0` 定义沪深300成分。回测输出使用 `default_universe`、`universes` 和统一产物表。
