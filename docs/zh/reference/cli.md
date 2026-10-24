# CLI 参考

没有 `--target` 时，start、exec、plugin 在本地处理，其他动作调用本机服务。显式 `--target` 将原始命令参数发送给远端 `cli` Job，由它通过 `python -m axonx.cli` 启动无 shell 子进程并转发 stdout、stderr 与退出码。远程路径属于目标机器，CLI 工作目录是服务 workspace。远程 start 和再次转发到其他目标会被拒绝。

## 命令分工

| 命令         | 执行位置              | 用途                                       |
| ------------ | --------------------- | ------------------------------------------ |
| axonx start  | 当前进程              | 启动 daemon 及 service／cron worker        |
| axonx exec   | 当前进程或显式 target | 执行同步 Task；无参数时列目录              |
| axonx JOB    | 所连服务              | 普通或流式 Job 调用                        |
| axonx plugin | 当前环境或显式 target | 插件检查、构建、安装与卸载                 |
| axonx help   | 所连服务              | 发现公开 Jobs；用 `--job NAME` 查询 schema |

本地 exec 不要求服务运行；远程 CLI 需要服务。进程隔离不构成安全沙箱。

## 能力发现与环境诊断

```bash
axonx
axonx help --target node-b:1024
axonx help --job python --target node-b:1024
axonx diagnose --target node-b:1024
```

无参数调用在本地显示用法，不依赖服务。顶层 `--help`、`-h` 已删除。`help` 保留为服务 Job，`--job NAME` 查询公开 Job schema。远程 CLI 要求目标服务公开经过认证的 `cli` Job。`diagnose` 查询构建、Python、workspace、资源、已安装插件和凭据配置布尔值。

## 启动与配置覆盖

```bash
axonx start
axonx start --config app.yaml
axonx start --config default --cron research
axonx start --config app.yaml --service.port 2024 --service.web-enabled false
axonx start --workspace-dir .axonx --log-dir logs
```

没有 --config 时 resolver 读取 default；配置文件继承、环境展开和合并见 [服务端配置](configuration.md)。不支持远程 `start`；`exec --target HOST:PORT` 在目标服务机器同步执行。

`--cron` 接受内置／安装包名称或明确的 `.cron` 文件路径，复用配置定位并使用独立的 `axonx.crons` entry-point 分组，启用本地五字段 `axonx exec --task` 调度。详见 [定时调度](../guides/scheduling.md)。

## Task 执行

```bash
axonx exec
axonx exec --task demo --task-name cli-demo --x 1 --y 2
```

本地 exec 不依赖 HTTP 服务，同步执行并输出 Task 结果，返回 Task 退出码。Task 将 metadata 写入配置的 workspace；观察服务应读取同一个 workspace。后台运行交给终端或进程管理工具。

```bash
axonx status --task-id 'base#demo#cli-demo' --detail full
axonx wait_task --task-id 'base#demo#cli-demo' --run-id '<metadata 中的 run_id>'
```

服务保留 Task 观察，不再提供专用提交、取消或删除 Task 的 Job。远程 `exec --target HOST:PORT` 仍属于同步远程 CLI 命令，断开请求或关闭该服务会终止其进程。

## 轻量查询默认值

| 查询                                       | CLI 默认返回                                  | 显式查询详情                                               |
| ------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------- |
| `list_task_statuses`                       | 所有传输方式默认摘要                          | `--detail full`；支持 `--task-type`、`--state` 过滤        |
| `status`、`wait_task`                      | Task/Run ID、状态、进度及管理归属摘要         | `--detail full` 查询输入、输出、子任务、产物及完整错误     |
| `list_installed_task_definitions`          | 注册信息，不生成 schema                       | `--include-schemas true`，或查询单个 `get_task_definition` |
| `read_task_log`                            | 末尾 8,192 字节                               | 显式 `--limit`（最多 262144）；绑定 `--run-id`             |
| `preview_file`                             | 20 行；文本/Markdown/JSON/YAML 字节预算 8,192 | `--limit`（最多 5000）、`--max-bytes`（最多 33554432）     |
| `list_agent_sessions`、`get_agent_session` | 20 条记录                                     | 显式 `--limit` 和 `--offset`                               |

这些有意调整的查询默认值不改变任务执行和持久化记录。HTTP/MCP 的 `status`、`wait_task` 默认仍为完整快照，Task 目录默认仍生成 schema。结构化文件被截断时只返回标记为部分内容的 UTF-8 前缀，不解析不完整的 JSON/YAML；检查 `truncated` 与 `parse_error`。CSV/JSONL/Parquet 使用行分页，与 `max_bytes` 独立。

```bash
axonx status --task-id 'base#demo#cli-demo' --detail full
axonx list_task_statuses --detail full --state failed
```

确认启动时轮询 `status`，核对返回的 Run ID、`queued`/`running` 状态与日志。`wait_task` 等待终态，短客户端超时不用于确认启动，也不会取消 Task。传输失败后保留原 ID，先查询再决定是否重新提交。HTTP 传输错误会标明异常类型、目标、接口和超时配置；HTTP 超时是各操作或无数据等待的限制，不是整个 Task 的截止时间。

## 参数与值转换

参数必须成对传递；布尔值也必须有值。连字符转下划线，点号建立嵌套字典。

CLI 自然值转换依次识别 null/none、布尔、整数/浮点、JSON，最后保留字符串。以零开头的数字避免直接数值转换，例如 000001 保留字符串。对象和数组建议单引号包裹合法 JSON，JSON 内使用双引号。

需要强制保留数字文本时用 JSON 字符串：

```bash
axonx agent_chat --message '"123"'
```

此处实际 message 是字符串 123；写 `--message 123` 会变成数字，并在字符串 Schema 下失败。空字符串可写 `--path ''`；#、空格、JSON 都建议引号。相同字段重复、父字段与嵌套字段冲突、缺值、`key=value` 与 `--field=value` 都不属于普通 Job 参数的合法写法。

## 客户端选项

| 选项             | 默认值                  | 含义                 |
| ---------------- | ----------------------- | -------------------- |
| --target         | null，默认连接本机 1024 | 直接连接目标服务     |
| --token          | null                    | 显式 Bearer token    |
| --client-timeout | 60                      | 请求预算，必须大于 0 |
| --stream         | false                   | 改用 SSE 入口        |
| --stream-format  | blocks                  | blocks 或 json       |

客户端选项可在 ACTION 前或后，但不能重复；不会进入 Job arguments。

```bash
axonx --target node-b:1024 version --token your-target-token
axonx version --target node-b:1024 --client-timeout 120
```

没有显式 token 时，无 target 读 AXONX_SERVICE_TOKEN，有显式 target 读 AXONX_TARGET_TOKEN。见 [客户端连接配置](client-configuration.md)。

## 流输出

```bash
axonx stream_task --task-id 'base#demo#cli-demo' \
  --stream true --stream-format blocks --client-timeout 600
axonx agent_chat --message '查看当前工作区的任务状态' \
  --stream true --stream-format json --client-timeout 600
```

本地 exec 的进程控制由执行环境负责，服务不提供 Task 取消或删除接口。断开只读观察请求不会改变独立任务的执行状态。

使用 `--task-id` 取消当前执行，或用 `--run-id` 精确取消某次执行。至少提供一个 ID；同时提供两个 ID 时，不匹配则返回 false。

## 插件子命令

plugin 使用 argparse 子语法，包含位置参数和 `-e` 布尔开关；它是普通成对 Job 选项规则的独立例外。

```bash
axonx plugin list
axonx plugin show axonx-example
axonx plugin inspect ./plugins/example
axonx plugin inspect ./dist/axonx_example-0.1.0-py3-none-any.whl
axonx plugin build ./plugins/example --output ./dist
axonx plugin install ./plugins/example
axonx plugin install -e ./plugins/example
axonx plugin uninstall axonx-example
```

没有 target 时，插件命令操作当前 Python 环境。有 target 时，所有插件子命令都在目标机器执行，包括 build 和 editable 安装。路径及 `--output` 均属于目标机器。`-e` 不能与 `--output` 同用。

本地源码先构建 wheel，再通过 `POST /upload` 上传，最后安装返回的绝对路径 `location`：

```bash
axonx plugin list --target node-b:1024
axonx plugin install /srv/axonx/.axonx/tmp/upload-id/example.whl \
  --target node-b:1024 --client-timeout 300
```

上传与安装分开；安装不删除输入文件，只修改 site-packages，不刷新服务已加载对象，也不追踪待重启状态。不协调并发环境修改。见[插件管理](../plugins/management.md)。

## 输出与退出码

| 退出码 | 情况                                                                   |
| ------ | ---------------------------------------------------------------------- |
| 0      | JobResponse.success=true，或本地操作成功                               |
| 1      | 业务失败、连接/运行错误；exec 可使用 Task 的具体退出码                 |
| 2      | 主 CLI 的 FileNotFoundError、KeyError、TypeError、ValueError；参数错误 |

普通 Job 打印完整 JSON；exec 打印 Task 输出而不是 JobResponse。失败时 stderr 可能含 `Error: 类型: 信息`。脚本应检查退出码，同时保留完整 response，区分“提交失败”与“任务后续失败”。

## 远程 CLI 协议

`POST /jobs/cli/events` 接收 `{"arguments":{"argv":["exec","--task","demo","--x","1","--y","2"]}}`。输出是 `channel=stdout` 或 `stderr` 的 `log` 事件；最终结果包含 `stdout`、`stderr`、`exit_code` 和截断标记。普通 JSON 接口每个输出通道最多保留 1 MiB；流式入口转发全部输出。CLI 原样回放输出并返回子进程退出码，不再包装一次 JSON。长操作设置 `--client-timeout`；输出不是心跳。

Task 执行与进程控制由 CLI 执行环境负责。服务通过 TaskRepository 读取已发布 metadata，不取消、恢复或接管 Task 进程。

## 相关文档

- [快速开始](../getting-started/quickstart.md)
- [任务 API](../api/tasks.md)
- [插件管理](../plugins/management.md)
- [现有开发速查](../dev_guide.md)

实现依据：`axonx/cli/parser.py`、`main.py`、`constants.py`、`plugin_kit/cli.py`。

## 服务自更新

[服务自更新](../guides/self-update.md)

`help` Job 仅返回公开 Job 名称、描述或单个 Job schema；CLI 使用说明由本地可执行入口拥有，运行不带参数的 `axonx` 查看。远程 CLI 子进程在命令入口拒绝启动服务和嵌套 target 转发。
