# Task 目录文件树

核对范围：`AxonX/axonx`、`AxonX/plugins`、`Axon/axon`、`Axon2/axon2`，共 **53 个 reg_name、9 种类型，合并为 19 组文件树**。核对时间：2026-10-30 20:54（上海）。

按数据与研究流程展示：`api → etl → train → predict → inference → portfolio → backtest → analysis → base`。同类型中，相同文件结构合并为一组，组内注册名与各组首个注册名均按字母排序。每组直接给出任务目录完整结构，内容或策略差异在组内说明。Qlib 指 AxonX 的三个研究插件。

`predict/inference` 分别对应离线与在线预测；因子分析也可在 ETL 后执行，`base` 负责整体编排。

路径相对 workspace。合并组用 `<reg_name>` 代表所列任一注册名；自动名字任务将 `tasks/` 换成 `tmp/tasks/`。`{a,b}` 表示多个文件，`<…>` 表示实际名称，可选文件按执行分支生成。

以下按正常执行后的代码约定列出文件；可选项和失败分支另行标注。所有树都包含运行记录：`metadata.json` 保存身份、状态、输入输出和子调用，`events.jsonl` 保存进度，`task.log` 在启用文件日志时生成；`persistent/task.lock` 是执行锁，`persistent/history.jsonl` 在每次执行结束后追加一行完整终态元信息 JSON。同名重跑保留 `persistent/`，清理其他旧文件。

业务文件索引位于 `metadata.output_params.artifacts`，窗口、在线 report.commit 和比较结果也可包含自己的 `artifacts`；路径相对其所属 Task 目录。在线父任务另用 `report.commit.protocol.input_sources` 引用推理子执行的完整证据。

数据表使用 `<名称>.parquet`，不加 `_stats`；CSV 仅用于统计报表，文件名必须以 `_stats.csv` 结尾。协议、模型索引、窗口和质量汇总保存在 metadata；模型原生文件、Markdown 报告和分层 JSON 报告使用各自格式。

Task 原位读取上游文件，`metadata.input_sources` 记录来源执行和文件修订。以下使用默认输出位置；`a_stock_etl` 指定外部 `output_dir` 时，Task 内的副本保留原文件名：`artifacts/{features,labels,market,calendar}.parquet` 和可选的 `artifacts/features_stats.csv`，以产物索引为准。展示同步目标可额外生成 `display/log.log`。

父子任务目录分别位于各自类型下，不互相嵌套；父任务通过 `children`、阶段 Task ID 和结果字段关联子任务。原始行情、Agent、daemon 等 Task 目录外文件不在本文范围。

## api：下载、采集与通知

### download_tushare_daily 等（11 个，同输出）

reg_name：`download_tushare_daily`、`download_tushare_etf_mins`、`download_tushare_hk_financial`、`download_tushare_static`、`download_tushare_stk_mins`、`download_tushare_task`、`download_tushare_us_financial`、`send_dingtalk_task`、`tushare_daily`、`tushare_financial`、`tushare_mins`。

来源：Axon2 / AxonX。Task 内仅运行记录。六个 Axon2 历史下载任务分别处理日频、ETF 分钟、港股财务、静态、股票分钟、美股财务，结果与计数保存在 metadata.output_params，原始文件写入共享数据目录。download_tushare_task 保存下载文件与行数；send_dingtalk_task 保存发送结果。三个 tushare_* 父任务编排对应下载子任务，汇总结果保存在 metadata。

```text
tasks/api/api#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
└── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
```

### download_tushare_realtime 等（2 个，同输出）

reg_name：`download_tushare_realtime`、`download_tushare_realtime_etf`。

来源：Axon2。分别采集股票和 ETF 窗口数据。同一 Task 的全部窗口平铺在同一个任务目录，不为窗口创建子任务或子目录。metadata.output_params.windows 保存窗口状态、行数、覆盖率、观测时间、文件修订与质量汇总；采集 Task 仍运行时，下游即可读取已完成窗口。任务名需包含交易日期才能分别保留每日数据。

```text
tasks/api/api#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── <窗口>_data.parquet                                     # 已完成窗口的数据
└── <窗口>_quality.parquet                                  # 可选，仅存在问题行时生成
```

## etl：数据与特征

### a_stock_etl 等（3 个，同输出）

reg_name：`a_stock_etl`、`v1_feature`、`v2_etl`。

来源：Axon / Axon2。A股特征。文件结构相同，特征内容与协议按家族变化。特征描述保存在 metadata.output_params.protocol，时刻使用 trade_time 字段，文件名和产物 key 固定。Axon 的 trade_time 固定为 1445，Axon2 按信号时间变化；Axon 的统计由 write_stats 控制，Axon2 需同时启用 write_stats 与 include_labels。

```text
tasks/etl/etl#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── features.parquet                                        # 特征、信号价格与资格
├── {labels,market,calendar}.parquet                        # 标签、独立行情和交易日历
└── features_stats.csv                                      # 可选全局统计
```

### qlib_a158_etl

reg_name：`qlib_a158_etl`。

来源：Qlib。Alpha158 特征。发布 158 个特征；列名、schema、日期范围和协议保存在 metadata。

```text
tasks/etl/etl#qlib_a158_etl#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── alpha158.parquet                                        # 特征与信号辅助字段
├── alpha158_stats.csv                                      # 特征质量统计
└── {labels,market,calendar}.parquet                        # 标签、独立行情和交易日历
```

### qlib_factor_etl

reg_name：`qlib_factor_etl`。

来源：Qlib。Alpha158 与上下文特征。沿用 alpha158 文件名，发布 171 个特征，并增加每日市场上下文诊断。

```text
tasks/etl/etl#qlib_factor_etl#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── alpha158.parquet                                        # 特征与信号辅助字段
├── alpha158_stats.csv                                      # 特征质量统计
├── {labels,market,calendar}.parquet                        # 标签、独立行情和交易日历
└── context_daily.parquet                                   # 每日市场样本数、收益均值与方差
```

### v1_merge

reg_name：`v1_merge`。

来源：Axon。14:45 数据合并。输出后续 V1 特征任务使用的合并数据；统计文件由 write_stats 控制。

```text
tasks/etl/etl#v1_merge#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── daily.parquet                                           # 14:45 合并数据
└── daily_stats.csv                                         # 可选质量与分布统计
```

## train：模型训练

### a_stock_train 等（3 个，同输出）

reg_name：`a_stock_train`、`v1_train`、`v2_train`。

来源：Axon / Axon2。单模型、多 seed 和 rolling 的一次训练计划始终只有一个训练 Task ID。metadata.output_params 索引模型配置、训练和使用日期、状态、样本数、指标、曲线与耗时。末组 use_to=null，持续预测后续日期。

```text
tasks/train/train#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 记录、模型索引、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
└── models/<类型>_seed_<种子>_fit_end_<截止日>_use_<起点>-<终点或onward>.pt
```

### qlib_a158_train 等（2 个，同输出）

reg_name：`qlib_a158_train`、`qlib_factor_train`。

来源：Qlib。LightGBM 训练。文件结构相同，factor 训练支持选择上下文特征。metadata 保存训练样本数、参数、验证指标、最佳轮数和曲线。

```text
tasks/train/train#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── models/lightgbm_seed_<种子>_fit_end_<截止日>_use_<起点>-onward.txt
└── feature_importance_stats.csv                            # gain/split 特征重要性
```

## predict：离线与滚动预测

### a_stock_predict 等（7 个，同输出）

reg_name：`a_stock_predict`、`a_stock_rolling_predict`、`qlib_a158_predict`、`v1_predict`、`v1_rolling_predict`、`v2_predict`、`v2_rolling_predict`。

来源：Axon / Axon2 / Qlib。默认文件结构相同。a_stock_predict、v1_predict、v2_predict 将全部日期、窗口和 seed 分数写入同一预测表；三个 rolling_predict 任务调用一个 train 子任务管理全部窗口模型，再调用一个 predict 子任务，父目录复制一份预测快照。qlib_a158_predict 使用 LightGBM 输出分数与排名。各任务的预测协议、分数映射和模型引用保存在 metadata.output_params.protocol，模型文件由训练 Task 持有。

```text
tasks/predict/predict#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、协议、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
└── predictions.parquet                                     # 全截面预测；滚动父任务保存子任务快照
```

## inference：在线推理

### a_stock_online_predict

reg_name：`a_stock_online_predict`。

来源：Axon2。在线推理子任务，窗口结果、输入特征和实际使用的模型快照保存在 outputs/。预测与特征协议、质量汇总、组合身份及文件索引位于 metadata.output_params.report.commit。按日 online 父任务复制展示表，并通过带 started_at 和文件修订的引用读取子执行证据；历史累计信号从此前每日父任务读取。

```text
tasks/inference/inference#a_stock_online_predict#<模型名>-<HHMM>/
├── {metadata.json,events.jsonl,task.log}
├── persistent/{task.lock,history.jsonl}
├── outputs/<HHMM>/
│   ├── {predictions,rankings,market,calendar}.parquet
│   ├── scores.parquet                                      # 可选，仅新增聚合分数
│   ├── {orders,positions,trades,daily,summary}.parquet    # 按 portfolio_key 区分组合，口径见文末
│   ├── corporate_actions.parquet                         # 使用证券事件评价器时生成的当日审计
│   ├── backtest_<资源名>.<扩展名>                         # 固定的评价政策输入，如 security_events.jsonl
│   ├── {input_features,features}.parquet
│   ├── quality_details.parquet                             # 可选，仅存在问题行时生成
│   ├── model/
│   │   ├── metadata.json                                   # 实际使用的训练模型集合
│   │   └── models/<已选模型>.pt                            # 对应模型文件
│   └── debug_{minute,daily,minute_panel,df}.parquet        # 可选，成功发布时复制调试数据
├── <窗口>_quality.parquet                                  # 可选，未完成窗口的问题明细
└── diagnostics/<窗口>/debug/                               # 可选，启用调试时按已有数据生成
    └── {minute,daily,minute_panel,df}.parquet
```

## portfolio：组合计划

### a_stock_portfolio 等（5 个，同输出）

reg_name：`a_stock_portfolio`、`qlib_a158_portfolio`、`qlib_strategy_portfolio`、`v1_portfolio`、`v2_portfolio`。

来源：Axon / Axon2 / Qlib。组合计划。文件结构相同，内容随分数选择/聚合、股票池、Top N 和策略变化。Qlib 使用全市场/沪深300，strategy 任务采用排名保留；Axon/Axon2 支持配置股票池与策略。原始分数和辅助字段原位引用 predict Task；所有组合共用 rankings.parquet，以 universe_key 区分股票池候选排名。仅实际聚合分数时新增 scores.parquet，单个原始分数直接引用上游列。metadata.output_params 保存股票池、分数列与 portfolios[] 组合身份和共享文件引用；目标按 target_rank <= top_n 派生，权重为 1/top_n。

```text
tasks/portfolio/portfolio#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── rankings.parquet                                        # 各股票池完整候选排名，共享
└── scores.parquet                                          # 可选，仅主键与新增聚合分数，共享
```

## backtest：组合回测

### a_stock_backtest 等（3 个，同输出）

reg_name：`a_stock_backtest`、`v1_backtest`、`v2_backtest`。

来源：Axon / Axon2。含证券事件的组合回测。执行上游 portfolio 计划，增加证券特殊事件处理与池内基准。回测序号从 0 开始，按本次选中组合顺序排列；对应身份和评估状态在 metadata.output_params.portfolios[]。

```text
tasks/backtest/backtest#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
└── portfolios/<回测序号>/                                  # 每个 portfolio_id 单独一套
    ├── daily.parquet                                       # 每日净值、收益、成本、持仓数量与诊断
    ├── summary.parquet                                     # 全区间、年度、季度、月度汇总
    ├── orders.parquet                                      # 成交与未成交订单、原因、金额和费用
    ├── positions.parquet                                   # 每日实际持仓、权重与延迟退出状态
    ├── trades.parquet                                      # 已平仓交易、收益与费用
    └── corporate_actions.parquet                           # 证券特殊事件处理账本
```

### qlib_a158_backtest

reg_name：`qlib_a158_backtest`。

来源：Qlib。组合回测。执行上游 portfolio 计划。每个组合对应独立结果目录，artifact 名为 `<回测序号>_<表名>`；通过 metadata.output_params.portfolios[] 对应 portfolio_id，可用 portfolio_ids 选择组合。

```text
tasks/backtest/backtest#qlib_a158_backtest#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
└── portfolios/<回测序号>/                                  # 每个 portfolio_id 单独一套
    ├── daily.parquet                                       # 每日净值、收益、成本、持仓数量与诊断
    ├── summary.parquet                                     # 全区间、年度、季度、月度汇总
    ├── orders.parquet                                      # 成交与未成交订单、原因、金额和费用
    ├── positions.parquet                                   # 每日实际持仓、权重与延迟退出状态
    └── trades.parquet                                      # 已平仓交易、收益与费用
```

## analysis：因子分析与比较

### a_stock_prediction_compare

reg_name：`a_stock_prediction_compare`。

来源：Axon2。逐窗口核对特征、预测、排名、Top N 目标、行情与组合账本。comparison.md 汇总各窗口结论；完成比对后生成 Top N 双侧对照，有预测值差异时另存有界样本。完整阶段统计及样本总数、上限、截断标记保存在 metadata.output_params.comparisons[]；缺失在线证据或协议不匹配时在 metadata 记录 missing 或 protocol_mismatch。

```text
tasks/analysis/analysis#a_stock_prediction_compare#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── comparison.md                                           # 各窗口结论与差异阶段
└── outputs/<YYYYMMDD>_<HHMM>/
    ├── differences.parquet                              # 可选，仅预测差异行，默认最多 200 行
    └── top_comparisons.json                              # 全市场/可买范围的 Top 5/10/20/30/50 双侧对照
```

### qlib_a158_analysis

reg_name：`qlib_a158_analysis`。

来源：Qlib。因子分析。metadata 另保存 scores、labels 和指标定义。

```text
tasks/analysis/analysis#qlib_a158_analysis#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── factor_analysis_stats.csv                               # IC、RankIC、覆盖、稳定性与排名
└── factor_quantiles_stats.csv                              # 分位组收益统计
```

### qlib_a158_compare

reg_name：`qlib_a158_compare`。

来源：Qlib。参数比较。编排训练、预测、portfolio、backtest 子任务；详细模型和账本位于各子任务目录。

```text
tasks/analysis/analysis#qlib_a158_compare#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
├── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
├── summary_stats.csv                                       # 按预设、标签及 portfolio_id 合并的回测汇总
└── comparison.json                                         # 配置、子任务身份、指标与输入版本
```

## base：研究、历史与日常编排

### a_stock_compare

reg_name：`a_stock_compare`。

来源：Axon2。按日留存各模型的 Top N 对照与按需预测差异样本；逐阶段指标和样本总数、上限、截断标记保存在 metadata.output_params.models[HHMM][模型名].comparison。通过 online 父任务的执行引用读取推理子任务的输入特征和模型；子证据被重跑覆盖后记录 missing。comparison.md 由 analysis 子任务持有，父任务复制窗口结果文件。

```text
tasks/base/base#a_stock_compare#<名称>-<YYYYMMDD>/
├── {metadata.json,events.jsonl,task.log}
├── persistent/{task.lock,history.jsonl}
└── outputs/<HHMM>/<模型名>/
    ├── top_comparisons.json                              # 全市场/可买范围的 Top 5/10/20/30/50 双侧对照
    └── differences.parquet                              # 可选，仅预测差异行，默认最多 200 行
```

### a_stock_history 等（7 个，同输出）

reg_name：`a_stock_history`、`a_stock_research`、`axon2_sync`、`demo`、`qlib_a158_research`、`v1_research`、`v2_research`。

来源：Axon2 / Axon / AxonX / Qlib。Task 内仅运行记录。a_stock_history 验证并复用历史输入，或调用 ETL 重建，metadata 保存 history_task_id、reused；四个 research 任务编排研究流程，业务文件保存在各阶段子任务；axon2_sync 保存同步 Job 响应，demo 保存算术结果。

```text
tasks/base/base#<reg_name>#<任务名>/
├── {metadata.json,events.jsonl,task.log}                   # 当前记录、进度、可选日志
└── persistent/{task.lock,history.jsonl}                    # 执行锁与跨重跑历史
```

### a_stock_online

reg_name：`a_stock_online`。

来源：Axon2。父任务采集公共窗口，按日留存每个模型的展示结果。各组合共享该模型的预测、排名和可选聚合分数，账本通过 portfolio_key 区分组合；键与完整身份保存在 metadata.output_params.models[HHMM][模型名].report.commit.protocol.report.portfolios。特征、模型、日历和调试文件由 inference 子任务持有，父任务保存执行引用；market 与每日信号表用于后续连续账本。

```text
tasks/base/base#a_stock_online#<名称>-<YYYYMMDD>/
├── {metadata.json,events.jsonl,task.log}
├── persistent/{task.lock,history.jsonl}
├── <窗口>_data.parquet                                   # snapshot、<HHMM>_before、<HHMM>_bar 等采集窗口
├── <窗口>_quality.parquet                                # 可选，公共采集质量明细
└── outputs/<HHMM>/<模型名>/
    ├── {predictions,rankings,market}.parquet
    ├── scores.parquet                                 # 可选，仅新增聚合分数
    ├── {orders,positions,trades,daily,summary}.parquet
    ├── corporate_actions.parquet                       # 可选，当日证券事件审计
    ├── backtest_<资源名>.<扩展名>                       # 评价实现声明的政策输入
    └── quality_details.parquet                        # 可选，模型质量明细
```

## 补充约定与源码

portfolio 的各组合共享排名和可选聚合分数，通过 `metadata.output_params.portfolios[]` 关联组合身份与文件。backtest 的结果序号按本次选中组合顺序从 0 开始，回测 artifact 名为 `<回测序号>_<表名>`。

online/compare 的模型配置共用显式 `etl[]`、`train`、`predict`、`portfolio`、`backtest`、`compare` 阶段，每项使用 `reg_name + task_name + params`，阶段名称可继承模型名。train 引用已有训练执行；在线 inference 复用 predict 的 GPU/启动参数并调用声明的 portfolio Task；compare 使用声明的预测、组合和比对任务。两者共用声明的 backtest 评价实现与政策文件快照。

portfolio 根据预测冻结组合计划；backtest 消费计划与独立行情，按组合保存全区间账本。在线 inference 及每日 online 父任务的账本以 portfolio_key 区分组合：positions 是当天完整持仓，orders/trades 是当天事件，daily 每个组合当天一行，summary 保留截至当天各统计区间；历史展示拼接每日记录。compare 调用独立 portfolio Task 核对身份与目标。

原子写入会短暂产生文件旁的 `.tmp`；Axon/Axon2 训练与预测的 `research-panel-*/` 内是 `.npy` 共享面板，在线推理使用 `.inference-*/`，外部特征适配使用 `axon-etl-*/`。这些过程目录正常结束后清理。

注册表：[框架内置](axonx/task/runtime/catalog.py)、[Alpha158](plugins/qlib_a158/axonx_qlib_a158/plugin.yaml)、[Factor](plugins/qlib_factor/axonx_qlib_factor/plugin.yaml)、[Strategy](plugins/qlib_strategy/axonx_qlib_strategy/plugin.yaml)、[Axon](../Axon/axon/plugin.yaml)、[Axon2](../Axon2/axon2/plugin.yaml)。

关键实现：[离线研究](../Axon2/axon2/research/)、[Axon 注册绑定](../Axon/axon/registrations.py)、[组合计划](axonx/task/builtins/stock/portfolio.py)、[组合回测](axonx/task/builtins/stock/backtest.py)、[online](../Axon2/axon2/a_stock/workflows/online.py)、[compare](../Axon2/axon2/a_stock/workflows/compare.py)、[在线推理](../Axon2/axon2/a_stock/tasks/online_predict.py)、[每日留存与证据引用](../Axon2/axon2/a_stock/storage.py)、[窗口比较](../Axon2/axon2/a_stock/tasks/prediction_compare.py)。
