# 服务部署与 Studio 托管

最小部署是一台机器上的 Python 服务、工作区和可选 Studio 包。先让带鉴权的 API 可用，再安装 Studio 和配置进程托管。以下进程托管与 HTTPS 是部署示例，需要按自己的系统调整。

## 安装与配置

要求 Python 3.12 或更高版本。创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install axonx
axonx help
```

创建 `server.yaml`：

```yaml
extends: default
workspace_dir: /srv/axonx/workspace
log_dir: /srv/axonx/logs
service:
  backend: http
  host: 127.0.0.1
  port: 1024
  token: ${AXONX_SERVICE_TOKEN}
  shutdown_timeout: 1
  web_enabled: true
```

绝对目录是 Linux 示例，不是项目默认路径。确保服务用户可以读写工作区与日志，并在相同环境安装需要的插件。

```bash
export AXONX_SERVICE_TOKEN='<独立服务 token>'
axonx start --config server.yaml
```

若需要其他机器直连，可改 host 为 `0.0.0.0`，并配置网络入口。默认配置本来监听这个地址，示例选择回环地址用于外部反向代理。

## 验证 API

```bash
curl -fsS 'http://127.0.0.1:1024/health' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
axonx version
axonx list_installed_task_definitions
```

设置 token 后，health 也需要 Bearer header。健康表示服务可响应，不证明模型 SDK、外部数据源或每个插件运行正常；继续用 demo 验证提交与等待。

## 安装并托管 Studio

执行 `pip install "axonx[studio]"`，然后重启服务。详见 [Studio 入门](../getting-started/studio.md)与[源码构建](../development/studio.md)。`web_enabled: false` 关闭页面托管，API 继续可用。

## 从仓库部署

准备 Python 3.12+ 和 Node/npm，并激活目标 Python 环境后，可以在任意目录执行 `bash /path/to/AxonX/scripts/deploy.sh`。脚本会切换到仓库根目录，从 `origin` 更新 `main`，执行 `npm ci` 并构建 Studio，从源码安装 AxonX 和 Studio 包，再以可编辑模式安装 `a158`、`a158_factor`、`a158_strategy` 三个插件。安装成功后，脚本停止监听 `1024` 端口的进程（必要时强制终止），最后在前台执行 `axonx start`。

脚本已有执行权限，在仓库根目录可直接运行 `./scripts/deploy.sh`。所有参数都会原样传给 `axonx start`，例如 `./scripts/deploy.sh --config remote` 最后执行 `axonx start --config remote`。端口清理仍针对 `1024`，不会读取指定配置。

macOS 下，脚本使用 `lsof` 查询监听进程，因为 `psutil` 的全系统连接查询需要 root 权限。请以普通用户运行脚本。查询结果受当前用户权限限制；空结果不保证没有高权限进程占用端口。查询失败时，脚本会中止部署并给出具体处理提示。停止进程时权限不足，脚本会发出警告、跳过该进程，继续执行 `axonx start`；如果端口仍被占用，启动可能失败。如果清理失败，或启动时提示 `1024` 端口被占用，请执行 `sudo lsof -nP -iTCP:1024 -sTCP:LISTEN`，确认列出的进程是旧服务，再用实际 PID 执行 `sudo kill -TERM <PID>`。端口释放后，在已激活的环境中运行 `axonx start` 即可，此时安装与构建已经完成。`sudo` 会要求输入登录密码，输入时不显示字符。不要使用 `sudo` 运行整个部署脚本。

## 后台进程托管示例

Linux 可使用 systemd，下面是最小 unit 示例。路径、账户和虚拟环境都需要替换：

```ini
[Unit]
Description=AxonX service
After=network.target

[Service]
Type=simple
User=axonx
WorkingDirectory=/srv/axonx/source
EnvironmentFile=/etc/axonx/service.env
ExecStart=/srv/axonx/source/.venv/bin/axonx start --config /etc/axonx/server.yaml
Restart=on-failure
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

service.env 保存所需环境变量，应限制读取权限。macOS 可使用自己的 launchd 配置；仓库不提供完整系统服务安装器。

## HTTPS 与事件流

内置 Uvicorn 服务没有 TLS 配置。可在 Caddy、Nginx 等外部入口终止 HTTPS，再代理到回环 HTTP 地址；客户端显式使用公开 HTTPS URL。

代理应保留 Authorization、请求体和正确的路径；SSE 入口应允许长连接，并避免响应缓冲。MCP 与 `/files` 也需要到达同一后端，上传入口限制应符合实际制品大小需求。

外部入口的超时、内置 shutdown_timeout、TaskManager 的 terminate_grace_seconds 和客户端 timeout 作用不同：分别控制代理等待、服务请求关闭、worker 停止宽限与调用等待。

## 更新与关闭

配置、Job 和插件贡献在应用装配时加载。修改后应重启服务，核对 version、插件列表、Task Schema 与 Studio assets 是否同一版本。

服务正常关闭会停止管理的 worker，并把相应运行记为 cancelled。重启不自动续跑这些研究任务。长训练升级前应先等待结束，或确认插件有可用的恢复方式。

迁移时先停止写入，复制工作区、日志与配置，恢复匹配插件环境，再核对历史记录与产物。不要只复制 Python 包而忽略实验文件。

[鉴权](authentication.md) · [运维与恢复](operations.md) · [配置参考](../reference/configuration.md) · [插件管理](../plugins/management.md)

源码：[HTTP 服务](../../../axonx/components/service/http/service.py)、[Studio 目录发现](../../../axonx/components/service/http/studio.py)、[TaskManager 关闭](../../../axonx/components/task_manager/local/manager.py)。
