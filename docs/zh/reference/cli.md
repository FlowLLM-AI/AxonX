# CLI 参考

## 命令职责

| 命令                    | 执行位置           | 结果                         |
| ----------------------- | ------------------ | ---------------------------- |
| `axonx`、`--help`、`-h` | 本地离线           | CLI 语法                     |
| `app`                   | 本地 Daemon 与服务 | 前台监督应用服务             |
| `exec --task NAME`      | 当前 CLI 进程      | 业务结果 JSON 和 Task 退出码 |
| `kill --task-id ID`     | 当前 CLI 环境      | 停止执行后的 Task metadata   |
| `plugin …`              | 当前 Python 环境   | 插件信息或安装结果           |
| 已配置的 Job 名         | 所选服务           | `JobResponse` JSON 或事件流  |

显式 `--target HOST:PORT` 通过目标服务的 `cli` Job 转发原生命令（`app`、`exec`、`kill`、`plugin`）。远端 CLI 拒绝 `app`、嵌套 `cli` 和继续转发到其他目标。普通 Job 直接连接所选服务。

## 能力发现与环境诊断

```bash
axonx help
axonx help --job cli
axonx diagnose
axonx exec
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
```

不带参数的 `exec` 离线列出当前解释器中的 Task。定义查询 Job 描述常驻服务的目录快照。新的 CLI 进程重新发现已安装插件；常驻服务需要重启才能重新读取注册快照和已缓存的类。

## 启动与配置覆盖

```bash
axonx app --config default
axonx app --config app.yaml --service.port 2024
```

点号参数构造嵌套字典。配置支持 `extends`、字典递归合并和列表整体替换，详见[配置参考](configuration.md)。

## 任务执行与观察

```bash
axonx exec --task demo --task-name check --x 1 --y 2
axonx status --task-id 'base#demo#check' --detail full
axonx wait_task --task-id 'base#demo#check' --client-timeout 600
axonx kill --task-id 'base#demo#check' --timeout 5 --force false
```

`exec` 同步执行。服务不可连接时可使用默认执行配置；认证、协议或 `get_config` 失败均报错。共享执行选项为 `workspace_dir`、`log_dir`、`timezone`、`execution_target`、`log_to_console`、`log_to_file` 和 `environment.KEY`。优先级为显式 CLI 参数 > 服务 `get_config` > 默认值。显式环境变量按键合并。

远程执行添加 `--target HOST:PORT` 并设置 `AXONX_TARGET_TOKEN`。原生命令实时传输 stdout/stderr，保留目标进程退出码。`--client-timeout` 控制连接，不是 Task 业务截止时间。中断远程命令请求可能终止它拥有的进程组，重试前先检查 metadata。

## 轻量查询默认值

CLI 的 `status`、`wait_task` 默认请求 `detail=summary`；文件预览默认 20 行、8192 字节；Agent 列表和历史默认 20 项。显式参数优先。Job 自身默认值可能不同，使用 `help --job NAME` 查询。

## 参数与值转换

使用 `--field value` 参数对。连字符转为下划线，点号生成嵌套字典。值会转换布尔值、null、数字、JSON 数组/对象和 JSON 引号包围的字符串。shell 中应引用包含 `#` 的 Task ID 和 JSON 数组。使用 `--upstream-task-ids '["etl#name#instance"]'` 声明依赖，不会自动执行上游。CLI `exec` 也接受逗号分隔的上游 ID。

## 客户端选项

`--target`、`--token`、`--client-timeout`、`--stream`、`--stream-format` 属于连接和显示选项，不是 Job 入参。默认超时 60 秒。地址必须包含端口，可使用 HTTP(S)，不允许路径、查询参数和内嵌凭据。本地 CLI 默认读取 `AXONX_SERVICE_TOKEN`，显式 target 读取 `AXONX_TARGET_TOKEN`；Python 客户端需显式传 token。

## 流式输出

```bash
axonx stream_task --task-id 'base#demo#check' --stream true --stream-format json
axonx agent_chat --message '检查工作区' --stream true
```

普通 Job 默认返回一次响应。流式调用使用 `/jobs/NAME/events`；`blocks` 便于阅读，`json` 每行一个事件。终态 `result` 包含 `success`、`answer`、`metadata`。远程原生命令始终传输进程输出，不依赖 `--stream` 开关。

## 插件子命令

```bash
axonx plugin list
axonx plugin show DISTRIBUTION
axonx plugin inspect ./plugins/qlib_a158
axonx plugin build ./plugins/qlib_a158 --output ./dist/plugins
axonx plugin install -e ./plugins/qlib_a158
axonx plugin uninstall DISTRIBUTION
```

使用 `--target` 时，路径在目标机解释，不会自动传输本地文件。从本机部署到远程必须显式构建 wheel、上传、用返回的绝对 `location` 安装，再用相对 `path` 清理。详见[插件部署](../plugins/management.md)。editable 需要执行机器上已有源码目录，不能与 `--output` 同用。

## 输出与退出码

Job 成功返回 0，失败返回 1。CLI 输入错误返回 2，其他执行错误返回 1。`exec` 输出业务结果并返回 Task 退出码。远程原生命令保留退出状态，负信号状态转换为 `128 + signal`。HTTP 成功不代表 Task 成功。

## 服务自更新

按服务配置调用 `update_from_git`、`update_from_pip`、`restart_service`、`get_update_status`。操作要求认证和 Daemon 支持，不接受 `force` 参数。详见[服务自更新](../guides/operations.md#服务更新与重启)。
