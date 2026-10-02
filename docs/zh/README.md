# AxonX 中文文档：默认配置与能力

本文以 [`axonx/config/default.yaml`](../../axonx/config/default.yaml) 为准，说明默认配置中声明的全部组件、任务及可选能力。`jobs` 中的任务已注册；以 `#` 注释的组件、任务和调度示例需要显式启用。配置文件中的任务描述是接口说明，实际可调用范围还受服务认证及任务参数约束。

## 启动与配置

需要 Python 3.12 或更新版本。安装项目后运行：

```bash
axonx start
```

启动时默认加载 `default` 配置。也可以用 `axonx start --config /path/to/config.yaml` 加载自己的 YAML 或 JSON 配置。自定义配置可通过 `extends: default` 继承默认配置；映射会递归合并。`${NAME}` 引用环境变量，`${NAME:-value}` 在环境变量不存在时使用后备值。CLI 也支持形如 `--service.port 1025` 的配置覆盖参数。

默认工作区为 `.axonx`，日志目录为 `logs`，时区为 `Asia/Shanghai`；这些值来自应用配置模型，并未在 `default.yaml` 中重复声明。

### HTTP 服务与访问控制

默认监听 `0.0.0.0:1024`，启用 Studio 网页界面（须存在构建好的静态资源）。`AXONX_SERVICE_SHUTDOWN_TIMEOUT` 控制关闭超时，默认 1 秒；`AXONX_SERVICE_WEB_ENABLED` 控制网页界面，默认 `true`；`AXONX_SERVICE_TOKEN` 设置服务令牌，未设置时为 `null`。

服务提供以下接口：

| 接口 | 作用 |
| --- | --- |
| `GET /health` | 查询服务运行状态 |
| `GET /jobs` | 列出可通过服务调用的任务 |
| `POST /jobs/{name}` | 执行任务；请求体为 `{"arguments": {...}}` |
| `POST /jobs/{name}/events` | 以 SSE 事件流执行任务 |
| `/mcp` | 通过 Streamable HTTP 暴露可公开的任务工具 |
| `POST /files`、`DELETE /files` | 上传文件到工作区暂存区、清理暂存文件 |
| `/proxy/{name}/...` | 将请求转发到已配置的同名代理组件 |

`/health`、`/jobs`、`/mcp` 和 `/files` 在配置令牌后使用 `Authorization: Bearer <token>`。`/proxy` 使用上游服务自己的认证。默认任务的 `requires_auth` 为 `true`，而默认令牌为 `null`：因此**未设置 `AXONX_SERVICE_TOKEN` 时，默认任务不会出现在 HTTP/MCP 公开任务列表中**。需要通过网络调用这些任务时，应设置服务令牌，并在客户端使用同一令牌。`web_enabled` 只控制 Studio 界面，不决定任务接口是否启用。

例如，在已设置服务令牌的环境中：

```bash
curl -H "Authorization: Bearer $AXONX_SERVICE_TOKEN" \
  http://127.0.0.1:1024/jobs

curl -H "Authorization: Bearer $AXONX_SERVICE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"arguments": {}}' \
  http://127.0.0.1:1024/jobs/version
```

命令行也可以把任务名作为命令执行，例如 `axonx version`。在命令末尾使用 `--target <host:port>` 直连目标服务；省略时连接 `127.0.0.1:1024`。还可传 `--token`、`--client-timeout` 和流式输出选项。`--client-timeout` 设置客户端请求超时；`shell` 的 `--timeout` 设置命令执行超时。使用 `axonx help` 查看完整格式。

## 默认组件

| 配置路径 | 默认设置与能力 |
| --- | --- |
| `targets` | 空列表；可配置供健康检查、Agent 工具和同步组件使用的目标服务。每项包含 `address`（`host:port`）和可选 `token`。CLI 的 `--target` 可直连服务，无须在此预先配置。 |
| `plugins.sources` | 空列表；可添加启动时加载的插件来源。相对路径相对于配置文件所在目录解析。 |
| `components.task_repository.default` | 本地任务仓库；递归监视工作区，使用轮询；防抖和扫描步长均为 3000 毫秒，轮询延迟 1000 毫秒。 |
| `components.task_manager.default` | 本地任务管理器，使用 `default` 任务仓库；终止宽限时间及回收检查间隔均为 5 秒。 |
| `components.agent.default` | Claude 后端的 AxonX 助手；会话状态目录 `agent/claude`，本地会话存储路径 `agent/session-store`，批量刷新存储。 |

Agent 从 `CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL`、`CLAUDE_CODE_MODEL_NAME` 填充对应的 Anthropic 环境变量。默认权限模式为 `bypassPermissions`，只加载工作区级 Claude 设置（`setting_sources: [project]`）。系统提示词规定其用户可见名称为 AxonX，并要求先使用工作区工具核实具体事实。默认提供给 Agent 的任务工具为 `list_entries`、`preview_file`、`list_task_ids`、`list_task_statuses`、`status`、`read_task_log`、`get_task_graph`、`get_task_context`。`skills` 和 Agent 插件配置仅作为注释示例，并未启用。

## 默认任务

下表列出 `default.yaml` 中所有**已启用**的任务。除特别说明外，任务可由本地任务调度调用；通过 HTTP/MCP 调用还须满足上一节的服务认证条件。参数中的路径均按对应任务说明解释，不能把任意系统路径当成工作区路径。

| 类别 | 任务 | 能力与主要参数 |
| --- | --- | --- |
| 系统 | `version` | 返回已安装的 AxonX 版本；无参数。 |
| 插件 | `list_plugins` | 列出已安装插件及其贡献；无参数。 |
| 插件 | `inspect_plugin` | 查看本机一个插件；必填 `plugin`（发行包名或插件名）。 |
| 插件 | `install_plugin` | 安装已上传到工作区的插件 wheel；必填 `path`（`POST /files` 返回的相对路径）和 64 位十六进制 `sha256`。 |
| 插件 | `uninstall_plugin` | 卸载本机插件发行包；必填 `plugin`。 |
| 机器 | `list_machines` | 检查所有已配置目标服务的健康状态；无参数。 |
| 机器 | `machine_status` | 获取本地或选定远程机器状态；无任务参数。CPU 采样间隔可在步骤配置中调整。 |
| 机器 | `shell` | 在选定机器执行 shell 命令；必填 `command`，可选 `timeout`（默认 30 秒，最大 300 秒）。 |
| 任务 | `list_installed_task_definitions` | 列出全部内置及插件 Task 的描述、类型及输入输出 schema；无参数。 |
| 任务 | `get_task_definition` | 查询一个 Task 的完整定义；必填 `task`（注册名，不是 Task ID 或实例名称）。 |
| 任务 | `submit` | 异步提交已注册 Task；必填 `task`，其他 Task 参数可一并传入。 |
| 任务 | `list_task_ids` | 列出有状态文件的 Task ID；无参数。 |
| 任务 | `list_task_statuses` | 列出 Task 状态快照；无参数。 |
| 任务 | `status` | 查询一个 Task 状态；必填 `task_id`。 |
| 任务 | `read_task_log` | 按字节读取 Task 日志；必填 `task_id`，可选 `offset`（默认 `-1`，负值表示读末尾）、`limit`（默认 65536，范围 1024–262144 字节）。 |
| 任务 | `get_task_context` | 返回一个 Task 的有限状态、路径和关联上下文；必填 `task_id`。 |
| 任务 | `stream_task` | 持续跟踪 Task 进度和日志，直到任务停止；必填 `task_id`，可选 `poll_interval`（默认 0.5 秒，必须大于 0）。 |
| 任务 | `get_task_graph` | 返回指定 Task 所在的依赖图；必填 `task_id`。 |
| 任务 | `cancel` | 取消排队中或运行中的 Task；必填 `task_id`。 |
| 任务 | `delete_tasks` | 删除已终止或仅有元数据的 Task 及其文件；必填非空、无重复的 `task_ids` 数组。 |
| 工作区 | `list_entries` | 列出工作区内一个目录；可选 `path`，空字符串表示工作区根目录。 |
| 工作区 | `list_task_runs` | 列出指定任务类型目录中带 `metadata.json` 的运行目录；必填 `task_type`（字母或数字开头，之后允许字母、数字、下划线和连字符）。 |
| 工作区 | `preview_file` | 预览工作区内受支持的文件；必填 `path`，可选 `offset`（默认 0）和 `limit`（默认 200，范围 1–5000），后两项用于 CSV、Parquet 等按行预览。 |
| 工作区 | `delete_entries` | 删除工作区内多个文件或目录；必填 `paths`，最多 200 项。 |
| 同步 | `sync_tasks` | 应用已上传的同步归档，并可先删除指定任务目录；可选 `path`、`deletions`（默认空数组，最多 200 项）。省略 `path` 时只应用删除。 |
| Agent | `agent_chat` | 执行一次交互式 Agent 会话轮次；必填 `message`，可选已有会话的 UUID `session_id`。步骤最大调用深度为 3。 |
| Agent | `list_agent_sessions` | 按最新优先列出会话；可选 `limit`（1–200）、`offset`（默认 0）。 |
| Agent | `get_agent_session` | 读取会话及可见消息历史；必填 UUID `session_id`，可选 `limit`（1–1000）、`offset`（默认 0）。 |
| Agent | `rename_agent_session` | 设置会话自定义标题；必填 `session_id`、非空 `title`。 |
| Agent | `tag_agent_session` | 设置或清除会话标签；必填 `session_id`、`tag`（字符串或 `null`）。 |
| Agent | `delete_agent_session` | 永久删除会话及其子 Agent 对话记录；必填 `session_id`。 |
| Agent | `fork_agent_session` | 复制会话，可选择截至某条消息；必填 `session_id`，可选 UUID `up_to_message_id`、非空 `title`。 |
| Agent | `cancel_agent_turn` | 中断会话正在运行的一轮；必填 `session_id`。 |

所有服务命令都可用 `--target` 直连目标服务。`install_plugin` 和 `uninstall_plugin` 默认要求认证，通过 HTTP/MCP 调用时须配置目标服务的 `service.token`，并在客户端提供匹配令牌。不带 `--target` 的 `axonx plugin install` / `uninstall` 直接操作当前 Python 环境，无需启动服务或配置令牌；带 `--target` 时通过 HTTP 操作指定服务。删除类任务会修改工作区或会话数据，使用前应确认传入的 ID 或路径。

插件 Task 的注册名可直接从 `axonx plugin list --target <host:port>` 返回的 `tasks` 映射键取得，先确认目标插件的 `error` 为空。需要所选 Task 的参数和默认值时，执行：

```bash
axonx get_task_definition --task a158_etl --target <host:port>
```

该命令通过 `POST /jobs/get_task_definition` 调用，HTTP 请求体为 `{"arguments": {"task": "a158_etl"}}`，响应的 `answer` 是单个定义对象，包含 `name`、`source`、`plugin`、`task_type`、`description`、`input_schema` 和 `output_schema`。单个查询只加载所选 Task；列表查询加载全部 Task，Studio 用完整列表生成提交表单。两者与提交使用同一注册解析逻辑，重复注册名（包括插件与内置 Task 重名）会报错，未知注册名也会报错。

不带 `--target` 的 `plugin list` 检查当前 CLI 的 Python 环境，定义查询和提交默认连接本机服务；服务使用不同环境时应显式指定相同目标地址。插件声明存在不保证 Task 能加载或执行。

## 可选能力：默认未启用

以下内容在 `default.yaml` 中为注释示例，不能只凭上述已注册任务推断它们已在运行：

| 配置 | 启用后的作用与条件 |
| --- | --- |
| `components.proxy.tushare` | HTTP 代理，将 `/proxy/tushare/...` 转发至 `AXONX_TUSHARE_BASE_URL`。可通过 `AXONX_TUSHARE_PROXY_TIMEOUT` 设置超时，示例默认 600 秒。必须提供上游地址。 |
| `components.sync.default` | 本地任务同步组件，依赖 `default` 任务仓库及已配置的目标服务；可配置启动时同步、Task ID/前缀筛选、每次归档数、文件与归档大小以及超时。示例值分别为 `sync_on_start: true`、每次最多 4 个归档、单文件 104857600 字节、归档 268435456 字节、超时 300 秒。 |
| `jobs.sync_flush` | 把待同步的任务变更刷新到目标工作区；示例关闭服务公开（`enable_serve: false`）。需要同步组件。 |
| `schedules.workspace_sync` | cron 调度 `sync_flush`，示例每分钟运行一次，并用 `concurrency_policy: forbid` 防止并发执行。启用前应同时启用同步组件和 `sync_flush`。 |
| `components.agent.default.skills` / `plugins` | 为 Agent 选择技能或本地插件；默认只保留了注释示例。 |

当前有效配置中的 `schedules: {}` 为空，没有默认定时任务。`sync_tasks` 虽然已注册，但它负责**接收并应用**归档；自动产生和发送变更需要另外启用同步组件、`sync_flush` 和调度。

## 扩展配置时的约定

- `components` 以“组件类型 → 实例名 → 后端及参数”组织，任务通过实例名引用组件，例如 `task_manager: default`。
- `jobs` 以任务名为键。每个任务可以声明 `description`、JSON Schema 格式的 `parameters`、顺序执行的 `steps`、`defaults`，以及 `enable_serve`、`enable_stream`、`requires_auth`。未显式配置时，后三项默认均为 `true`。
- `schedules` 以调度名为键，指定 `backend`、`job`、`cron`，并可设置 `arguments`、`timezone`、`concurrency_policy`（`forbid`、`allow`、`replace`）。
- `targets` 的 `address` 必须是有效且不重复的 `host:port` 或 HTTP(S) URL；端口范围为 1–65535。

完整参数和当前默认值请以 [`default.yaml`](../../axonx/config/default.yaml) 为准。
