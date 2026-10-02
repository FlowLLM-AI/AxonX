# CLI 参考

AxonX 的命令格式是 `axonx ACTION --field value`。start、exec、plugin、help 在本地处理；其他 ACTION 是服务 Job 名。先配置连接 token，再根据 [公开目录](../api/overview.md) 选择 Job。

## 命令分工

| 命令 | 执行位置 | 用途 |
| --- | --- | --- |
| axonx start | 当前进程 | 启动配置中的服务 |
| axonx exec | 当前进程 | 执行同步 Task；无参数时列目录 |
| axonx submit | 所连服务的 worker | 通过 submit Job 异步提交 |
| axonx JOB | 所连服务 | 普通或流式 Job 调用 |
| axonx plugin | 当前环境或显式 target | 插件检查、构建、安装与卸载 |
| axonx help | 当前进程 | 语法速查 |

exec 不要求服务运行；submit 需要服务。进程隔离不构成安全沙箱。

## 启动与配置覆盖

```bash
axonx start
axonx start --config app.yaml
axonx start --config app.yaml --service.port 2024 --service.web-enabled false
axonx start --workspace-dir .axonx --log-dir logs
```

没有 --config 时 resolver 读取 default；配置文件继承、环境展开和合并见 [服务端配置](configuration.md)。客户端 --target/--client-timeout 不能用于 start 或 exec。

## Task 执行与提交

```bash
axonx exec
axonx exec --task demo --x 1 --y 2
axonx exec --task demo --x 1 --y 2 --task-name local-demo

axonx list_installed_task_definitions
axonx get_task_definition --task demo
axonx submit --task demo --x 1 --y 2 --task-name cli-demo
```

submit 输出通用 JobResponse；保存 answer.task_id 与 answer.run_id，替换下方占位：

```bash
axonx wait_task --task-id 'base#demo#cli-demo' \
  --run-id YOUR_RETURNED_RUN_ID --client-timeout 600
axonx status --task-id 'base#demo#cli-demo'
axonx read_task_log --task-id 'base#demo#cli-demo' --offset -1 --limit 65536
```

wait_task 的最终 success 取决于任务是否 succeeded。submit 成功只表示接受并启动，不能立即假定 metadata 已发布。固定名称重跑会替换终态目录，活跃任务不能覆盖。

## 参数与值转换

参数必须成对传递；布尔值也必须有值。连字符转下划线，点号建立嵌套字典。

```bash
axonx submit --task demo --x 1 --y 2 --fail false
axonx start --service.port 2024
axonx delete_tasks --task-ids '["base#demo#cli-demo"]'
axonx delete_entries --paths '["tmp/example.txt"]'
```

CLI 自然值转换依次识别 null/none、布尔、整数/浮点、JSON，最后保留字符串。以零开头的数字避免直接数值转换，例如 000001 保留字符串。对象和数组建议单引号包裹合法 JSON，JSON 内使用双引号。

需要强制保留数字文本时用 JSON 字符串：

```bash
axonx agent_chat --message '"123"'
```

此处实际 message 是字符串 123；写 `--message 123` 会变成数字，并在字符串 Schema 下失败。空字符串可写 `--path ''`；#、空格、JSON 都建议引号。相同字段重复、父字段与嵌套字段冲突、缺值、`key=value` 与 `--field=value` 都不属于普通 Job 参数的合法写法。

## 客户端选项

| 选项 | 默认值 | 含义 |
| --- | --- | --- |
| --target | null，默认连接本机 1024 | 直接连接目标服务 |
| --token | null | 显式 Bearer token |
| --client-timeout | 60 | 请求预算，必须大于 0 |
| --stream | false | 改用 SSE 入口 |
| --stream-format | blocks | blocks 或 json |

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

blocks 适合终端阅读；json 每行一个事件模型 JSON，可供程序处理。最终 result 的 success 决定退出码。中断消费者不等于取消后台研究 Task；明确取消：

```bash
axonx cancel --task-id 'base#demo#cli-demo'
```

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

没有显式 target 时插件操作针对当前 Python 环境，不默认连接本机 HTTP 服务。有显式 target 时 list、show、inspect、install、uninstall 针对服务环境；远程 install 的源目录或 wheel 在客户端先构建/检查再上传。

```bash
axonx plugin list --target node-b:1024
axonx plugin install ./plugins/example --target node-b:1024
```

build 只在本地，不能配远程 target。editable 只支持本地源码目录，不能配 target 或 output；已有 wheel 不能配 output。远程安装客户端超时至少 300 秒。插件变更后查看 restart_required，重启服务再发现新贡献。

## 输出与退出码

| 退出码 | 情况 |
| --- | --- |
| 0 | JobResponse.success=true，或本地操作成功 |
| 1 | 业务失败、连接/运行错误；exec 可使用 Task 的具体退出码 |
| 2 | 主 CLI 的 FileNotFoundError、KeyError、TypeError、ValueError；参数错误 |

普通 Job 打印完整 JSON；exec 打印 Task 输出而不是 JobResponse。失败时 stderr 可能含 `Error: 类型: 信息`。脚本应检查退出码，同时保留完整 response，区分“提交失败”与“任务后续失败”。

## 相关文档

- [快速开始](../getting-started/quickstart.md)
- [任务 API](../api/tasks.md)
- [插件管理](../guides/plugin-management.md)
- [现有开发速查](../dev_guide.md)

实现依据：`axonx/cli/parser.py`、`main.py`、`constants.py`、`plugin_kit/cli.py`。
