# 配置参考

## 最小覆盖配置

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
timezone: Asia/Shanghai
language: zh
service:
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
cron: []
```

```bash
axonx app --config app.yaml --service.host 127.0.0.1
```

## ApplicationConfig

应用字段为 `workspace_dir`、`log_dir`、`timezone`、`execution_target`、`environment`、`command`、`app_name`、`bind_host`、`transfer_budget_bytes`、`language`、`enable_logo`、`log_to_console`、`log_to_file`、`targets`、`cron`、`components`、`jobs` 和可选 `service`。未知顶层字段会被拒绝。默认传输预算 512 MiB、语言 `en`、时区 `Asia/Shanghai`。启动层注入 `command` 供服务启动 CLI 子进程。

执行 CLI 参数优先于服务解析后的 `get_config`，再回退 `ExecutionSettings` 默认值。`get_config` 返回绝对工作区/日志路径、执行环境和解析后的应用配置。该接口要求认证，可能含环境变量值，应作为配置数据处理，不作为公开诊断报告。

## 配置发现与继承

`ConfigLoader` 支持 YAML、YML、JSON。`--config` 接受路径、内置名称（`default`、`remote`）或已安装的 `axonx.configs` 入口。带扩展名的相对路径先查当前工作目录，再查内置配置目录。命名来源必须唯一，与内置名称冲突会报错。

`extends` 接受父配置名称/路径或有序列表。存在的相对父文件按声明文件所在目录解析。字典递归合并，列表和标量替换，循环继承报错。选择自定义文件不会隐式继承 `default`，需要时显式写 `extends: default`。

## 环境变量展开与路径

CLI 启动从工作目录或父目录加载 `.env`，不覆盖已有环境变量。插值支持 `${NAME}`、`${NAME:-default}`。普通工作区和日志路径在执行进程中解析，不应假设相对于 YAML 文件。命名配置入口在目标包中定位配置文件。

## ComponentConfig 与命名组件

```yaml
components:
  task_index:
    default:
      backend: local
      poll_interval: 5
  machine:
    default:
      backend: local
```

类别选择能力域，`default` 是实例名，`backend` 选择 provider。当前域包括 agent、task_index、machine、proxy、sync、updater。依赖通过有类型的基类和实例名声明。Job、service、step 使用各自字段，Cron 使用顶层 `cron`。

## JobConfig

Job 支持 `backend`（默认 `pipeline`）、`description`、JSON 对象 `parameters`、`enable_serve`、`enable_stream`、`requires_auth`、`steps`、`defaults`。Step provider 选项与公共入参独立；系统注入字段单独校验，调用方不能传入。ComponentConfig 保留后端额外选项。公开能力由服务开关和认证配置共同决定。

pipeline 后端支持 `event_buffer_size`（正整数，默认 64）和 `cancel_on_disconnect`（布尔值，默认 true）。设置 `cancel_on_disconnect: false` 后，调用方断连时执行继续由服务管理。后台持续消费输出并丢弃无人订阅的事件，直到调用结束或 Job/应用关闭才释放管理。内置 `cli` Job 将该选项设为 false，其他 Job 默认在断连时取消。显式停止远程研究执行使用 Task `kill`。

## CronConfig

```yaml
cron:
  - expression: "0 16 * * 1-5"
    command:
      - axonx exec --task download_tushare_task
      - --days-back 7
```

`command` 接受一个字符串或字符串片段列表。列表先用空格拼接，再统一解析整条命令；每个计划只执行一条命令。包含空格的值和 JSON 参数须在命令文本内加引号，例如 `--models '{"0945": [{"task_name": "model-0945"}]}'`。长片段可用 YAML `>-` 块换行，通过锚点在多个计划间复用完整的带引号参数。每个片段都必须是字符串，加载后保存为拼接后的命令字符串。

CLI 启动只支持五字段数字 cron 和本地 `axonx exec --task NAME`。命令不经 shell，拒绝客户端连接选项。列表整体替换继承计划。触发使用应用时区，不补跑错过时点，配置变化需重启。详见[调度](../guides/scheduling.md)。

## TargetConfig

```yaml
targets:
  - address: http://node-b:1024
    token: ${NODE_B_TOKEN}
```

地址必须含端口并被规范化，重复地址或未知字段会报错。后端只向已配置目标转发并读取对应凭据。显式 CLI target 使用 CLI 凭据直接连接，无需列入本地服务配置。

## HTTP 服务

`service.backend: http` 暴露 Job、事件、MCP、`/upload` 和可选 Studio。常用字段包括 `host`（回退 `bind_host`）、`port`、`token`、`web_enabled`、`shutdown_timeout`、`cleanup_timeout`。前台 Daemon 收到 Ctrl+C 或 SIGTERM 后，整体退出上限固定为 5 秒，即使 `cleanup_timeout` 更长也不例外。配置 token 后才能暴露认证能力。代理路由使用上游认证。详见[认证](../guides/authentication.md)和[部署](../guides/deployment.md)。

源码：[模型](../../../axonx/app/config/models.py)、[加载器](../../../axonx/app/config/loader.py)、[默认配置](../../../axonx/app/config/default.yaml)。
