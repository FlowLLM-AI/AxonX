# AxonX Harness 中文 Skill 编写 Prompt

请基于当前 AxonX 仓库编写一份供量化研发 Agent 使用的中文 Harness Skill。先核对 `axonx/cli/`、`axonx/plugin_kit/`、`axonx/config/default.yaml`、`axonx/task/`、`axonx/steps/` 和 `plugins/a158/`，以代码中的命令、参数、返回值与默认配置为准；若代码变化，更新下表，不要照抄过时文档。正文按“背景 → Task 类型 → 插件开发与运行闭环 → CLI API”连续展开；解释性文字每处最多三句，步骤、分类和命令均用“类型｜描述｜命令”三列表格，命令列写可直接执行的完整示例。

## 1. 背景

用**恰好三句话**介绍：AxonX 是面向金融量化研发的 Harness 框架；它统一 ETL、Analysis、Train、Predict、Backtest 等 Task 的注册、提交、运行和产物管理；Agent 可专注插件代码与研究结果，机器选择、远程提交、状态和日志由框架提供。

## 2. Task 类型

用三列表格解释以下类型，命令列使用当前仓库已注册的 `a158_*` 名称，不把 Task 类别误写成 CLI 子命令。

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| ETL | 清洗与对齐数据，构建特征和标签，生成下游数据集。 | `axonx submit --task a158_etl --task-name demo --start-date 20150101` |
| Analysis | 读取成功的 ETL 产物，做因子诊断和统计分析。 | `axonx submit --task a158_factor --task-name demo --source-tasks 'etl#a158_etl#demo'` |
| Train | 使用 ETL 数据训练模型，保存模型和训练指标。 | `axonx submit --task a158_train --task-name demo --source-tasks 'etl#a158_etl#demo'` |
| Predict | 使用已训练模型和数据生成预测文件。 | `axonx submit --task a158_predict --task-name demo --source-tasks 'train#a158_train#demo'` |
| Backtest | 使用预测结果评估策略，输出回测指标和文件。 | `axonx submit --task a158_backtest --task-name demo --source-tasks 'predict#a158_predict#demo'` |

`source_tasks` 使用英文逗号分隔的 Task ID 字符串；单个 ID 直接填写，留空表示无上游。

表中的 `demo` 由 `--task-name demo` 指定；实际运行时用前序 `submit` 返回的真实 `task_id` 替换。下游依赖来自 `source_tasks`，不要把 `run_id` 当作上游 Task ID。

## 3. 插件开发与运行闭环

说明一个插件仓库可以完整承载五类 Task，当前示例是 `plugins/a158` 的 `plugin.yaml` 和 Python 实现。Agent 的主要代码动作空间是插件 Git 仓库：可以直接修改已有实现，也可以在该仓库内复制一套平行 Task 列表并在 `plugin.yaml` 注册；新增 Task 名称与入口必须和代码一致。解释 Task 提交通过 HTTP 连接本地或远程 AxonX 服务；`axonx plugin` 不带 `--target` 时直接操作当前 Python 环境，带 `--target` 时通过 HTTP 操作目标服务。插件安装与 Task 提交是两个独立动作。

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 1. 修改代码 | 在插件 Git 仓库中修改或新增 ETL、Analysis、Train、Predict、Backtest，核对 `plugin.yaml` 注册与输入输出契约。 | `git -C plugins/a158 status --short` |
| 2. 本地安装 | 将当前插件源码构建为 wheel，直接安装到当前 Python 环境；无需启动服务或配置令牌。 | `axonx plugin install plugins/a158` |
| 3. 远程安装 | 将同一源码构建为 wheel，通过 HTTP 上传并安装到目标 AxonX 服务；默认插件 Job 要求认证，目标服务需配置 `service.token`，客户端提供匹配的访问令牌。 | `axonx plugin install plugins/a158 --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 4. 确认插件 | 查看本地 Python 环境或目标服务已安装的插件，确认目标插件 `error` 为空，从 `tasks` 映射键选取 `--task`；需要参数说明时查询单个定义。 | `axonx plugin list`；`axonx plugin list --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024`；`axonx get_task_definition --task a158_etl --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 5. 选择机器 | 用户未指定机器时，先查已配置节点的健康状态，再分别查候选机器的 CPU、内存、GPU；`list_machines` 仅返回健康状态。 | `axonx list_machines`；`axonx machine_status`；`axonx machine_status --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 6. 远程提交 | 直连选定目标服务提交 Task，记录返回 `answer.task_id` 和 `answer.run_id`。 | `axonx submit --task a158_etl --task-name demo --start-date 20150101 --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 7. 跟踪与排错 | 使用同一目标服务查询状态、等待结束和读取日志；失败后回到第 1 步，修复、重装、重提。 | `axonx status --task-id 'etl#a158_etl#demo' --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024`；`axonx read_task_log --task-id 'etl#a158_etl#demo' --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 8. 验收产物 | 状态为 `succeeded` 后查看该 Task 目录中的 `metadata.json`、输出文件；必要时用 `preview_file` 抽查。 | `axonx list_entries --path 'etl/etl#a158_etl#demo' --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024`；`axonx preview_file --path 'etl/etl#a158_etl#demo/metadata.json' --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |

在步骤表后用不超过三句话说明：默认 `targets: []`，所以 `list_machines` 可能为空；所有服务命令在末尾用 `--target <host:port>` 直连目标服务，省略时连接 `127.0.0.1:1024`。`axonx plugin` 省略 `--target` 时直接操作当前 Python 环境；通过 HTTP 调用默认插件 Job 时，目标服务需配置 `service.token`，客户端需提供匹配的令牌。

## 4. 完整 CLI API

按下列分组输出“类型｜描述｜命令”三列表格，覆盖当前默认配置中除 Agent 会话相关 Job 之外的全部 CLI 与 Job；不要介绍 `agent_chat` 或 proxy 能力。示例中的 `etl#a158_etl#demo`、`run-001`、工作区路径和目标地址均为示例值，实际执行时替换成服务返回值；JSON 数组参数作为一个 shell 参数传入。服务命令在末尾使用 `--target <host:port>`，普通 Job 参数放在 Job 名之后。

### 启动与本地执行

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 帮助 | 显示 CLI 用法。 | `axonx help` |
| 启动 | 启动本地 HTTP 服务。 | `axonx start` |
| 指定配置启动 | 使用自定义应用配置。 | `axonx start --config axonx/config/default.yaml` |
| 本地任务目录 | 在本机 Python 环境列出可执行 Task。 | `axonx exec` |
| 本地执行 Task | 在本机直接执行已注册 Task，不经过远程 `submit`。 | `axonx exec --task a158_etl --start-date 20150101` |
| 版本 | 查询所连接服务的 AxonX 版本。 | `axonx version` |

### 插件管理

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 列出插件 | 查看本机已安装插件。 | `axonx plugin list` |
| 查看插件 | 查看一个已安装插件。 | `axonx plugin show axonx-alpha158` |
| 检查插件 | 检查当前环境已安装的插件；源码可用 `plugin build` 构建并检查 wheel。 | `axonx plugin inspect axonx-alpha158` |
| 构建插件 | 在本地构建并检查 wheel。 | `axonx plugin build plugins/a158` |
| 本地安装 | 从源码构建 wheel，直接安装到当前 Python 环境；无需启动服务或配置令牌。 | `axonx plugin install plugins/a158` |
| 远程安装 | 直连目标服务上传并安装 wheel；默认需在目标服务配置 `service.token` 并提供匹配令牌。 | `axonx plugin install plugins/a158 --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 本地卸载 | 卸载当前 Python 环境中的插件。 | `axonx plugin uninstall axonx-alpha158` |
| 远程插件查询 | 通过目标服务查询已安装插件。 | `axonx plugin show axonx-alpha158 --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 远程插件卸载 | 从目标服务卸载插件；默认需在目标服务配置 `service.token` 并提供匹配令牌。 | `axonx plugin uninstall axonx-alpha158 --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 插件 Job | 直接查询服务中的插件列表与详情。 | `axonx list_plugins`；`axonx inspect_plugin --plugin axonx-alpha158` |
| 安装 Job | 安装已上传到目标工作区的 wheel；一般使用上面的 `plugin install` 完成上传和 SHA-256 校验。 | `axonx install_plugin --path 'tmp/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef/alpha158.whl' --sha256 '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'` |
| 卸载 Job | 通过服务卸载插件；默认需在目标服务配置 `service.token` 并提供匹配令牌。 | `axonx uninstall_plugin --plugin axonx-alpha158` |

### 机器与远程连接

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 已配置机器 | 查看配置节点的地址和健康状态。 | `axonx list_machines` |
| 本机资源 | 查看当前连接服务机器的 CPU、内存、GPU。 | `axonx machine_status` |
| 指定机器资源 | 直连指定机器的 AxonX 服务查看资源。 | `axonx machine_status --token "$AXONX_SERVICE_TOKEN" --target 192.0.2.10:1024` |
| 指定目标 | 直连目标服务执行 Job。 | `axonx machine_status --target 192.0.2.10:1024` |
| 远程命令 | 在所连接服务的机器上执行 shell 命令。 | `axonx shell --command 'pwd' --timeout 30` |

### Task 提交与运行

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 可用 Task | 浏览服务中全部内置及插件 Task 的完整定义。 | `axonx list_installed_task_definitions` |
| 单个 Task 定义 | 查询所选 Task 的描述、类型及输入输出 schema；`--task` 填注册名。 | `axonx get_task_definition --task a158_etl` |
| 提交 Task | 异步提交，读取返回的 `answer.task_id` 和 `answer.run_id`。 | `axonx submit --task a158_etl --task-name demo --start-date 20150101` |
| 等待指定运行 | 同一 `task_id` 可对应新的 `run_id`；等待时两者都要传。 | `axonx wait_task --task-id 'etl#a158_etl#demo' --run-id 'run-001' --client-timeout 86400` |
| 实时跟踪 | 流式查看 Task 进度和日志。 | `axonx --stream true stream_task --task-id 'etl#a158_etl#demo'` |
| Task ID 列表 | 列出有状态文件的 Task ID。 | `axonx list_task_ids` |
| 状态列表 | 列出 Task 状态快照。 | `axonx list_task_statuses` |
| 单个状态 | 查看一个 Task 的当前状态与结果。 | `axonx status --task-id 'etl#a158_etl#demo'` |
| 任务日志 | 按字节读取日志，默认读取末尾。 | `axonx read_task_log --task-id 'etl#a158_etl#demo' --offset -1 --limit 65536` |
| Task 上下文 | 查看 Task 状态、路径和关联上下文。 | `axonx get_task_context --task-id 'etl#a158_etl#demo'` |
| 依赖图 | 查看 Task 与上游任务的关系。 | `axonx get_task_graph --task-id 'etl#a158_etl#demo'` |
| 取消 | 取消排队或运行中的 Task。 | `axonx cancel --task-id 'etl#a158_etl#demo'` |
| 删除 | 删除已终止或只有元数据的 Task 及文件。 | `axonx delete_tasks --task-ids 'etl#a158_etl#demo'` |

### 工作区与同步

| 类型 | 描述 | 命令 |
| --- | --- | --- |
| 列出目录 | 查看工作区根目录或指定相对路径。 | `axonx list_entries --path ''` |
| 运行目录 | 列出某 Task 类型下有 `metadata.json` 的运行目录。 | `axonx list_task_runs --task-type etl` |
| 预览文件 | 查看工作区内 JSON、CSV、Parquet 等受支持文件；CSV/Parquet 可按行抽查。 | `axonx preview_file --path 'etl/etl#a158_etl#demo/metadata.json'` |
| 删除条目 | 删除工作区相对路径指向的文件或目录。 | `axonx delete_entries --paths 'etl/etl#a158_etl#demo/old.csv'` |
| 应用同步归档 | 将已上传的同步归档应用到本机工作区；这是接收端 Job，默认自动同步组件未启用。 | `axonx sync_tasks --path 'tmp/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef/tasks.zip'` |

写作时保持命令与行为对应：`list_machines` 不提供资源指标，`machine_status` 才提供；`metadata.json` 在成功运行后写入 `工作区/<task_type>/<task_id>/metadata.json`；`preview_file` 读取工作区相对路径。不要臆造上传归档路径、目标服务或运行 ID 为真实存在的资源，也不要在 Skill 中要求 Agent 无条件执行删除、取消或 shell 命令。
