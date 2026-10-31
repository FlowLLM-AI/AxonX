# Qlib Factor

[English](README.md) · [简体中文](README_ZH.md)

`qlib_factor` 是离线特征研究插件，为 Alpha158 ETL 增加 13 个可选的市场矩、中性动量和风险特征，共输出 171 个特征列。训练按组选择，默认空分组列表使用 158 个基础特征。下方示例选择 `risk`，共 160 个特征。

训练继承基础插件的截止日隔离、末尾 10% 日期早停与全训练期重拟合。特征分析、预测、组合构建和回测复用基础插件。

## 因子与时点

| 分组     | 特征数 | 定义                                         |
| -------- | -----: | -------------------------------------------- |
| mean     |      4 | 各窗口收益截面缩尾均值，反映市场整体涨跌方向 |
| variance |      4 | 各窗口收益截面缩尾样本方差，反映股票涨跌分歧 |
| neutral  |      3 | 5/10/20 日 beta 调整动量                     |
| risk     |      2 | 20 日特质波动与下行风险                      |

每只股票收益为复权 C(T)/C(T−h)−1，h=1/3/5/10 个市场交易日。两个端点须有报价且成交量、成交额和复权价格为正；包含涨跌停股票，不使用未来标签或可交易性筛选。各日期、各窗口独立用 2%/98% 线性分位缩尾，再计算等权均值与样本方差（ddof=1）。空股票池保留缺失，单股票方差缺失。方差描述截面分歧；均值接近零并不能单独证明多数股票震荡。

全局矩在 T 收盘后可用，同日所有股票共享相同值；动量/风险因子随股票变化。全局矩不能用单因子截面 IC 判断，应比较模型消融。定义见 [features.py](axonx_qlib_factor/features.py)；ETL 保存各窗口样本数和每日因子值。

`context_groups` 是由 `mean`、`variance`、`neutral`、`risk` 组成的列表。默认 `[]` 仅使用 158 个基础特征，示例选择 `["risk"]`。不支持的组名和上下文特征列会在校验时报错。

`context_windows` 可选择 `[1,3,5,10]` 的非空子集，默认全部四个窗口。ETL 发布全部 13 列，context_windows 只过滤全局均值/方差；个股组使用固定窗口。消融复用同一数据集，训练协议记录实际窗口。例如 `--context-groups '["mean","variance"]' --context-windows '[10]'` 只加入两个 10 日因子。

Beta 使用 T−1 及之前 60 个市场日，至少需要 30 个股票与市场配对收益。股票日收益按当日 2%/98% 分位缩尾，市场收益为其等权均值。Beta 为协方差除以市场方差，并限制在 [−3,3]；方差 ≤1e−12 时保持空值。中性动量为股票 5/10/20 日累计收益减去历史 beta × 市场累计收益。残差波动为“股票日收益 − 历史 beta × 市场日收益”的 20 日样本标准差；下行风险为 sqrt(mean(min(股票日收益,0)²))。风险窗口至少需要 20 日内 16 个有效观测；当日行情无效时所有股票特征保持空值。

ETL 在输出起点之前预读 80 个市场日，使 20 日风险窗口中的每个历史残差都拥有之前 60 日的 beta 历史；信号资格仍要求 60 日历史。源数据历史充分时，重叠日期的特征不随输出起点改变。

插件版本 0.3.0 要求 Python 3.12+、AxonX `>=0.3.1` 和上游研究插件 `>=0.3.0`。按依赖顺序安装，研究产物使用协议 v1。

## 安装与执行

研究插件尚未发布到 PyPI。先克隆仓库并从根目录安装 AxonX 0.3.1 主包（`pip install -e .`），以下命令从仓库根目录执行。本机 Agent 开发按依赖顺序安装到执行服务的 Python 环境：

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
```

远程安装与服务刷新见[插件管理](../../docs/zh/plugins/management.md)。以下示例需准备插件、数据与 `AXONX_TARGET_TOKEN`，并将 `http://research.example:1024` 替换为实际服务地址。

```bash
axonx get_task_def --task qlib_factor_train --target http://research.example:1024

axonx exec --task qlib_factor_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx exec --task qlib_factor_train --upstream-task-ids '["<etl_task_id>"]' \
  --train-start 20150101 --train-end 20230101 \
  --label-column label_return_rank --parameter-preset axonx \
  --context-groups '["risk"]' --feature-fraction 1.0 --target http://research.example:1024
axonx exec --task qlib_a158_predict --upstream-task-ids '["<train_task_id>"]' \
  --pred-start 20230101 --pred-end 20261008 --target http://research.example:1024
axonx exec --task qlib_a158_portfolio --upstream-task-ids '["<predict_task_id>"]' --top-ns '[5,10,20,30]' --target http://research.example:1024
axonx exec --task qlib_a158_backtest --upstream-task-ids '["<portfolio_task_id>"]' --as-of-date 20261008 --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

从执行日志或 `status --detail full` 保存 Task ID 和 `started_at`；仅在退出码为零且状态为 `succeeded` 后提交下游。`qlib_a158_analysis` 可作为增强 ETL 的因子诊断分支。安装修改所选解释器；新 CLI 进程发现已安装插件，定义查询和 Studio 则保留服务启动时的目录，直到重启。安装或核验失败时停止并报告。[Qlib Alpha158](../qlib_a158/README_ZH.md)

## 执行与配置

使用标准 `axonx app` 配置。本插件注册 `qlib_factor_etl` 和 `qlib_factor_train`，其余阶段复用 `qlib_a158_analysis`、`qlib_a158_predict`、`qlib_a158_portfolio` 和 `qlib_a158_backtest`。日期、特征组和模型参数在每次执行时传入。预测可指定一个 Train 和一个可选兼容 ETL，用已有模型预测新数据。

## 本地验证

在仓库根目录安装全部三个研究插件及开发依赖后执行：

```bash
python -m pytest plugins/qlib_factor/tests plugins/qlib_a158/tests tests/unit/test_stock_backtest.py -q
```

研究测试使用临时合成行情执行因子和策略链路，覆盖产物交换和显式选择预测 ETL。

## 实验记录

共享设定、结果、复现命令和 Task 来源统一维护在 [Alpha158 改进实验](../../docs/zh/research/alpha158-case.md)。产物字段与股票池报告遵循[共享协议](../../docs/zh/reference/research-artifacts.md)。
