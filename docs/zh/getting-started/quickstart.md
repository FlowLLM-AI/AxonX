# 快速开始

在 macOS 或 Linux 上使用 Python 3.12+。先运行内置 Demo，再安装研究插件。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
axonx --help
```

只安装 `axonx` 可获得后端；`studio` extra 添加预构建 UI。研究插件需要从本仓库单独安装。

## 配置并启动服务

在启动目录的 `.env` 或 shell 中设置服务 token，然后启动应用：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

默认端口为 `1024`，工作区为 `.axonx`，时区为 `Asia/Shanghai`。前台 Daemon 监督应用服务。保持此终端运行，另开终端并使用相同 Python 环境和 token 执行后续命令。Studio 地址为 `http://127.0.0.1:1024`。

启动 Logo 和服务控制台输出会显示在此终端，同时保存到 `.axonx/daemon/<identity>/service.log`，服务重启后继续显示。Ctrl+C 会停止 Daemon 和服务，并终止服务拥有的手动 CLI 命令，整体退出上限为 5 秒。已经启动的定时命令继续独立运行，后续定时触发停止。

## 发现并执行 Demo

```bash
axonx help
axonx list_task_defs --include-schemas false
axonx get_task_def --task demo
axonx exec --task demo --task-name quickstart --x 1 --y 2
```

`exec` 等待任务完成，输出业务结果 JSON，并以 Task 的退出码结束。Demo 返回和 `3`，Task ID 为 `base#demo#quickstart`。需要保留独立结果时使用不同的 `task_name`。

## 等待并检查结果

```bash
axonx status --task-id 'base#demo#quickstart' --detail full
axonx read_task_log --task-id 'base#demo#quickstart'
axonx get_task_graph --task-id 'base#demo#quickstart'
```

长任务执行期间可在另一个终端观察。`wait_task --task-id ID --client-timeout 600` 等待当前执行，期间 `started_at` 改变会报错。CLI 的 status 和 wait 默认返回摘要；检查输入输出时使用完整详情。查询不会修复失效记录。

## 检查持久化记录

当前记录位于 `.axonx/tasks/base/base#demo#quickstart/metadata.json`，包含 `started_at`、状态、进程身份、步骤、输入输出参数和子任务调用。Task 状态为 `running`、`succeeded`、`failed`。启用文件日志时，Task 日志保存在自身目录的 `task.log`，`log_path` 为 Task 相对路径；服务日志仍使用独立的 `log_dir`。

显式同名重跑会在旧执行停止后替换当前文件，并保留 `persistent/`。任务目录不是不可变的执行历史。停止活动执行使用 `axonx kill --task-id ID`，详见[任务管理](../guides/task-management.md)。

## 在当前进程执行

`exec` 的执行配置依次取 CLI 参数、服务 `get_config`、内置默认值。只有连接失败才回退默认值。没有服务也可执行；需要指定工作区时传 `--workspace-dir`。使用 `--target HOST:PORT` 时，由目标服务的认证 `cli` Job 在目标机启动命令，所有路径均属于目标机。

## 下一步

- [插件安装与远程部署](../plugins/management.md)
- [研究流程](../research/workflow.md)
- [内置 Agent](../agent/configuration.md)
- [配置参考](../reference/configuration.md)
