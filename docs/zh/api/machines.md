# 机器、配置与维护 API

检查所选解释器、机器和应用。诊断输出报告凭据是否配置，不返回凭据值。

遵循 [HTTP/MCP 协议](overview.md)，通过 `axonx help --job NAME` 查询 Schema。示例 Task/会话 ID 需替换为实际值。

## 接口列表

| Job                 | 用途                                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| `shell`             | 运行 Bash 命令和上传脚本；客户端断开后继续执行。                                                           |
| `help`              | 列出本服务公开的 Job，或查询某个 Job 的输入输出 Schema；CLI 连接选项不属于业务参数。                       |
| `diagnose`          | 检查本服务的构建、Python 环境、工作区磁盘和资源使用情况；不返回凭据值。                                    |
| `version`           | 返回当前安装的 AxonX 版本。                                                                                |
| `get_config`        | 返回已解析的应用配置，包括调度、执行默认值与环境；执行目录为绝对路径。                                     |
| `list_machines`     | 检查所有已配置远程 AxonX 服务的健康状态。                                                                  |
| `machine_status`    | 读取所选 AxonX 服务的机器状态。                                                                            |
| `python`            | 在所选服务的全新解释器进程中执行多行 Python，使用服务已安装的依赖。                                        |
| `update_from_git`   | 停止服务，从当前分支的上游快进更新，构建并安装 AxonX 与 Studio，再重启服务；正在执行的定时 Task 继续运行。 |
| `update_from_pip`   | 停止服务，从包索引升级 axonx 与 axonx-studio，再重启服务；正在执行的定时 Task 继续运行。                   |
| `restart_service`   | 重启应用并重新加载配置和调度；停止服务拥有的手动命令，保留定时 Task。                                      |
| `get_update_status` | 读取更新记录与日志尾部；省略 update_id 时读取最近一次更新。                                                |

## shell

在服务环境中运行 Bash 源码或上传的脚本。可选 `cwd` 指定远程已存在的工作目录，相对路径基于工作区解析。该普通 pipeline Job 设置 `cancel_on_disconnect: false`，客户端断开后继续执行，服务关闭时终止进程组。

```json
{
  "arguments": {
    "command": "printf 'hello\\n'",
    "cwd": "."
  }
}
```

完成后返回 `stdout`、`stderr`、`exit_code`、`stdout_truncated` 和 `stderr_truncated`；SSE 持续传输 stdout/stderr。不创建单独的执行记录，事后通过 Task 记录或显式重定向的 Shell 日志观察。执行脚本前先通过 `/upload` 上传，使用返回的 `answer.location`。

## help

列出本服务公开的 Job，或查询某个 Job 的输入输出 Schema；CLI 连接选项不属于业务参数。

| 参数  | 类型     | 必填 | 默认/约束         |
| ----- | -------- | ---- | ----------------- |
| `job` | `string` | 否   | `{"minLength":1}` |

```json
{
  "arguments": {
    "job": "cli"
  }
}
```

## diagnose

检查本服务的构建、Python 环境、工作区磁盘和资源使用情况；不返回凭据值。

无业务参数。

```json
{
  "arguments": {}
}
```

## version

返回当前安装的 AxonX 版本。

无业务参数。

```json
{
  "arguments": {}
}
```

## get_config

返回已解析的应用配置，包括调度、执行默认值与环境；执行目录为绝对路径。

无业务参数。

```json
{
  "arguments": {}
}
```

返回已解析的应用/执行配置，含绝对执行目录及环境，可能含环境变量值，要求认证。

## list_machines

检查所有已配置远程 AxonX 服务的健康状态。

无业务参数。

```json
{
  "arguments": {}
}
```

## machine_status

读取所选 AxonX 服务的机器状态。

无业务参数。

```json
{
  "arguments": {}
}
```

## python

在所选服务的全新解释器进程中执行多行 Python，使用服务已安装的依赖。

| 参数      | 类型     | 必填 | 默认/约束                                           |
| --------- | -------- | ---- | --------------------------------------------------- |
| `code`    | `string` | 是   | `{"minLength":1}`                                   |
| `timeout` | `number` | 否   | `{"exclusiveMinimum":0,"maximum":300,"default":30}` |

```json
{
  "arguments": {
    "code": "print(1 + 2)",
    "timeout": 30
  }
}
```

在服务端新解释器进程执行源码，不是持久 Python 会话。返回 stdout/stderr、exit_code 和截断信息，仅执行请求范围内的操作。

## update_from_git

停止服务，从当前分支的上游快进更新，构建并安装 AxonX 与 Studio，再重启服务；正在执行的定时 Task 继续运行。

无业务参数。

```json
{
  "arguments": {}
}
```

## update_from_pip

停止服务，从包索引升级 axonx 与 axonx-studio，再重启服务；正在执行的定时 Task 继续运行。

无业务参数。

```json
{
  "arguments": {}
}
```

## restart_service

重启应用并重新加载配置和调度；停止服务拥有的手动命令，保留定时 Task。

无业务参数。

```json
{
  "arguments": {}
}
```

## get_update_status

读取更新记录与日志尾部；省略 update_id 时读取最近一次更新。

| 参数        | 类型     | 必填 | 默认/约束                      |
| ----------- | -------- | ---- | ------------------------------ |
| `update_id` | `string` | 否   | `{"pattern":"^[0-9a-f]{32}$"}` |

```json
{
  "arguments": {}
}
```

## 维护结果

更新/重启响应表示接受操作，并返回 update_id。重连后查询 get_update_status，接受不代表完成。服务拥有的手动命令随服务停止，Daemon 定时任务继续。不接受 force 入参。详见[服务自更新](../guides/operations.md#服务更新与重启)。

源码：[默认 Job 契约](../../../axonx/app/config/default.yaml) · [Job 协议](overview.md)
