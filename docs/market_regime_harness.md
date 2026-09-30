# AxonX 量化开发与任务使用速查

## 一、开发插件到任务成功

| 步骤 | 操作与命令 | 判断与下一步 |
| --- | --- | --- |
| 1. 明确特征 | 例如按 `trade_date` 计算市场涨跌、上涨家数占比、成交额变化，再合并到当日个股特征。收盘后信号可使用当日收盘数据；更早的信号只能使用此前已知的数据。 | 当前 `daily`、`stk_limit`、沪深 300 权重可支持市场涨跌、宽度、流动性；严格的小盘特征还需新增逐日市值数据。 |
| 2. Agent 开发 | `axonx agent_chat --message '修改 a158 插件，增加逐日市场环境特征，验证时点并运行测试' --stream true`；在插件中实现 Task、输入输出参数和步骤，并在 `plugin.yaml` 注册新任务。 | 默认 Agent 工作目录是 `.axonx`，开发仓库源码前应将 `components.agent.default.cwd` 指向仓库。默认 Agent 的 `job_tools` 不含 `submit`、`wait_task`；要让它直接调用这两个 Job，需加入配置。 |
| 3. 测试与安装 | 运行相关测试；用 `axonx plugin install plugins/a158 --target <IP>:1024` 将插件安装到执行 Task 的服务，再查询已注册 Task。 | 目标机器须具备插件依赖和所需数据。 |
| 4. 提交 | `axonx submit --task <任务名> --<参数> <值>`，例如 `axonx submit --task a158_etl --start-date 20150101`。 | 记录返回的 `task_id` 和 `run_id`；正确语法是 `axonx submit`，不是 `axonx --submit`。 |
| 5. 等待与查看 | `axonx wait_task --task-id '<task_id>' --run-id '<run_id>' --timeout 86400`；需要实时日志时用 `axonx stream_task --task-id '<task_id>' --stream true`。 | `succeeded` 才进入下游；`failed` 或 `cancelled` 转入排错。 |
| 6. 排错并重提 | `axonx status --task-id '<task_id>'`、`axonx read_task_log --task-id '<task_id>'`、`axonx get_task_graph --task-id '<task_id>'`；据错误修改代码、补测试、重新安装插件、再执行 `submit`。 | 新提交会有新的 `run_id`；命名 Task 可能复用 `task_id`。重复“提交 → 等待 → 查状态与日志 → 修复”，直到成功。 |
| 7. 成功验收 | 检查 `status.answer.result`、`metadata.json` 和输出文件；必要时用 `preview_file` 抽查，再将成功的上游 `task_id` 传给训练或回测任务。 | 保留产物、配置和 Task ID，便于复现。 |

## 二、Task 类型

| `TaskType` | 用途 | 当前示例 |
| --- | --- | --- |
| `base` | 通用计算任务。 | `demo` |
| `api` | 获取外部数据。 | `download_tushare_task` |
| `etl` | 清洗、对齐数据并生成特征／标签。 | `a158_etl`；市场环境特征适合在此阶段加入。 |
| `analysis` | 因子诊断与统计分析。 | `a158_factor` |
| `train` | 训练模型。 | `a158_train` |
| `predict` | 离线批量预测。 | `a158_predict` |
| `inference` | 在线推理类别。 | 默认未注册对应实例。 |
| `backtest` | 用预测结果做策略回测。 | `a158_backtest` |

## 三、Job 与单机／远程调用

| Job／命令 | 用途与示例 | 单机、远程及默认限制 |
| --- | --- | --- |
| 调用形式 | `axonx <job> --<参数> <值>`；Task 由 `submit` Job 异步创建。 | 服务有令牌时传 `--token <TOKEN>`；在命令末尾加 `--target <IP>:1024` 直连目标服务。 |
| `agent_chat` | 让 Agent 分析工作区并开发代码：`axonx agent_chat --message '...' --stream true`。 | 在所连接服务的 Agent 工作目录执行；默认 `job_tools` 只有文件预览、Task 状态／日志／关系等查询，不含提交与等待。 |
| `plugin list`、`get_task_definition`、`list_installed_task_definitions`、`submit` | 从目标服务插件列表的 `tasks` 键选取注册名；`axonx get_task_definition --task <注册名> --target <IP>:1024` 查询所选 Task 的完整定义，列表接口用于浏览全部定义；`axonx submit --task <任务名> ... --target <IP>:1024` 创建 Task。 | 新增插件须先安装到目标服务。 |
| `wait_task`、`stream_task`、`status`、`read_task_log` | 等待最终结果、实时跟踪、查状态与日志；失败后用日志定位，再重新提交。 | `wait_task` 要同时传 `task_id`、`run_id`；长任务提高客户端 `--timeout`。 |
| `get_task_graph`、`get_task_context`、`list_entries`、`preview_file` | 查上游关系、任务上下文和工作区产物。 | `preview_file` 仅做有限行预览，不能代替全量 Parquet 计算。 |
| `shell`、插件／同步 Job | `shell` 在服务机器执行命令；插件 Job 管理安装；同步 Job 管理工作区归档。 | 默认 Agent 工具列表不含 `shell`；默认插件 Job 要求认证，未配置 `service.token` 时不通过 HTTP/MCP 暴露，客户端需提供匹配令牌；不带 `--target` 的 `axonx plugin` 命令直接操作当前环境，无需服务令牌；自动同步、定时调度未启用。 |
| 目标地址 | `axonx submit --task <任务名> --target <IP>:1024` 直连目标服务。 | 省略 `--target` 时连接 `127.0.0.1:1024`；[`default.yaml`](../axonx/config/default.yaml) 的 `targets: []` 仅表示未预设后台检查或同步目标。 |
