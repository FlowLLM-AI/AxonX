# 机器、配置与维护 API

检查所选解释器、机器和应用。诊断输出报告凭据是否配置，不返回凭据值。

所有下列 Job 使用 `POST /jobs/NAME` 和 `{"arguments": {...}}` 请求体。流式入口为 `/jobs/NAME/events`，MCP 使用相同 Job 名和业务参数。先调用 `help --job NAME` 获取目标服务实际 Schema。示例中的 Task/会话 ID 必须替换为实际值。

![机器选择](../../figures/api/machine-target.svg)

## 接口列表

| Job                 | 用途                                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
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

更新/重启响应表示接受操作，并返回 update_id。重连后查询 get_update_status，接受不代表完成。服务拥有的手动命令随服务停止，Daemon 定时任务继续。不接受 force 入参。详见[服务自更新](../guides/self-update.md)。

源码：[默认 Job 契约](../../../axonx/app/config/default.yaml) · [Job 协议](overview.md)
