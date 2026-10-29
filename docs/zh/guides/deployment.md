# 服务部署与 Studio 托管

使用 Python 3.12+，在独立环境安装后端和可选 Studio。daemon 监督一个 service；Cron 在 service 内运行。进程托管器应管理 `axonx app` 启动的 daemon，service 子进程由 daemon 管理。

## 安装与配置

```bash
python -m venv .venv
source .venv/bin/activate
pip install 'axonx[studio]'
```

创建 `server.yaml`，按部署机器调整路径：

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
service:
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
  shutdown_timeout: 1
  cleanup_timeout: 15
cron: []
```

```bash
export AXONX_SERVICE_TOKEN='<独立服务 token>'
axonx app --config server.yaml
```

需要其他机器直连时可绑定 `0.0.0.0` 并配置网络入口。工作区、日志和启动目录应可读写；研究插件安装在同一 Python 环境。配置定时任务见[定时调度](scheduling.md)。

## 验证

```bash
curl -fsS 'http://127.0.0.1:1024/health' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
axonx version
axonx list_task_defs --include-schemas false
axonx exec --task demo --task-name deployment-check --x 1 --y 2
axonx status --task-id 'base#demo#deployment-check'
```

health 表示服务就绪；demo 检查实际执行与观察。API 可在未安装 Studio 时运行；安装 Studio 后重启 service，打开 `http://127.0.0.1:1024/`。

## 远程接入

目标需要自己的服务、解释器、插件、数据和工作区。CLI 直连目标；Studio 经后端转发。

### CLI 直连

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx plugin list --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

普通 Job 直接调用目标，原生命令通过 cli 转发 argv。Exec 等待完成、传输目标 stdout/stderr 并保留退出码。保留 target、Task ID、started_at 以继续观察。默认 cli Job 在连接关闭后继续执行。通过 status、wait_task 或 stream_task 观察，重试前先检查记录。服务关闭仍会停止其手动命令。

### Studio 后端转发

在本地服务 targets 列表配置目标地址和 token，Studio 选中机器并发送传输层 target，由后端读取凭据。业务参数不能覆盖路由凭据，各目标状态和 Agent 会话独立。

### 远程文件与插件

原生命令路径均在目标服务工作区解释，包括 plugin install/build/inspect 的源码路径。--target 不上传本地文件。本地构建 wheel、上传 /upload、安装返回的绝对 location、清理相对 path，再重启常驻服务刷新 Task 目录，详见[插件部署](../plugins/management.md)。

### 连通性、资源与停止

list_machines/machine_status/diagnose 提供观察到的资源，不自动调度机器。Kill 使用 metadata 的源 execution_target 和 workspace_dir。展示副本不能控制源进程，machine_id 也不是地址。

## 从仓库部署

在激活的执行环境中运行 `./scripts/deploy.sh [应用选项]`，例如 `./scripts/deploy.sh --config server.yaml`。脚本切换到仓库根目录，相对配置路径以此为基准。要求 Git、Python 和 Studio 支持的 Node.js/npm。

脚本使用与 `axonx app` 相同的配置解析和服务标识，验证 daemon 锁、监督器命令及 service 父进程后，先停止所选 daemon 与 service。它随后快进当前分支的 upstream、构建 Studio、以 editable 模式安装后端和 Studio、执行 `pip check`，再安装三个研究插件，最后在前台运行 `axonx app` 并传入原应用选项。不会根据端口选择并终止任意监听者。

停止或身份核验失败时，脚本在更新源码前退出。拉取、构建或安装失败时停止部署，需要修复后重新启动；脚本不回滚源码或环境。通过 systemd/launchd 托管时，应先使用托管器停止 daemon，完成部署后仍通过托管器启动，避免两个监督器竞争。

## 后台托管示例

```ini
[Unit]
Description=AxonX daemon
After=network.target

[Service]
Type=simple
User=axonx
WorkingDirectory=/srv/axonx/source
EnvironmentFile=/etc/axonx/service.env
ExecStart=/srv/axonx/source/.venv/bin/axonx app --config /etc/axonx/server.yaml
Restart=on-failure
KillMode=process
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

替换账户和路径，限制环境文件权限。此示例的 `KillMode=process` 将 daemon 作为停止目标，由 daemon 关闭 service，避免托管器直接终止同组外的定时进程；独立定时进程可能在完整 daemon 停止后继续运行，需要按 Task 身份显式管理。macOS 可使用自行配置的 launchd；仓库没有完整系统服务安装器。

## HTTPS 与事件流

TLS 在外部反向代理终止。代理应保留 Authorization、请求体、重复头与正确路径，支持 `/mcp`、`/upload` 和长时间 SSE，并关闭事件流缓冲。代理与客户端超时、Uvicorn 请求收尾及 service 总关闭期限是不同预算。

## 更新与关闭

通过 `axonx restart_service` 重新加载源码、`.env`、Task 定义和 Cron 配置；`update_from_git`、`update_from_pip` 在更新后自动启动新 service。daemon PID 保持不变，service PID 改变。监督器源码或启动 argv 发生变化时，需要停止并重新启动整个 `axonx app`。详见[服务更新与重启](operations.md#服务更新与重启)。

前台 daemon 显示本次运行的服务控制台输出，包括启动 Logo，同时保留 `workspace_dir/daemon/<identity>/service.log`。服务重启后继续输出，重新启动 daemon 不回放旧日志。

在启动终端按 Ctrl+C，或向 daemon 发送 SIGTERM，会停止 daemon 并请求 service 关闭。这会停止 Cron 接受新触发，清理组件并终止 service 创建的手动 CLI 子进程。daemon 已启动的定时命令继续独立运行。daemon 从第一次 Ctrl+C 或 SIGTERM 起限制整体退出时间为 5 秒，包含服务清理、更新进程退出和控制台日志收尾。到期强制结束剩余服务及更新进程组，并立即退出；重复信号不会延长期限。即使 `cleanup_timeout` 更长，此上限仍然有效；该配置仍用于仅重启服务时的服务清理期限。强制终止可能留下 running metadata，观察查询不改写记录；后续执行前的身份检查或显式 kill 负责确认退出后的收尾。定时 Task 不因 service 重启而重跑，也不补跑停机期间的时刻。

迁移前协调所有写入进程，再复制工作区、配置和必要日志并恢复相同插件环境。

实现：[daemon](../../../axonx/daemon/supervisor.py)、[部署停止工具](../../../scripts/stop_daemon.py)、[HTTP 服务](../../../axonx/app/components/service/http/service.py)。
