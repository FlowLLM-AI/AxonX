# 服务部署与 Studio 托管

最小部署是一台机器上的 Python 服务、工作区和可选 Studio 包。先让带鉴权的 API 可用，再安装 Studio 和配置进程托管。以下进程托管与 HTTPS 是部署示例，需要按自己的系统调整。

## 安装与配置

源码环境要求 Python 3.12 或更高；Studio 构建要求 Node.js 22.13+（22.x）、24.x 或 26+。在仓库根安装：

```bash
uv sync
uv run axonx help
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
uv run axonx start --config server.yaml
```

若需要其他机器直连，可改 host 为 `0.0.0.0`，并配置网络入口。默认配置本来监听这个地址，示例选择回环地址用于外部反向代理。

## 验证 API

```bash
curl -fsS 'http://127.0.0.1:1024/health' \
  -H "Authorization: Bearer $AXONX_SERVICE_TOKEN"
uv run axonx version
uv run axonx list_installed_task_definitions
```

设置 token 后，health 也需要 Bearer header。健康表示服务可响应，不证明模型 SDK、外部数据源或每个插件运行正常；继续用 demo 验证提交与等待。

## 安装并托管 Studio

```bash
python -m pip install axonx-studio
```

重启服务后，AxonX 从 Studio Python 包加载页面。未安装 Studio 时仅跳过页面托管，API 继续工作。`web_enabled: false` 关闭页面托管，不影响 Job、MCP 或文件接口。

从源码部署时，先在 `axonx_studio/` 执行 `npm ci` 和 `npm run build`，再从仓库根目录执行 `python -m pip install ./axonx_studio`。Vite 开发服务器仅用于前端开发；见 [Studio 入门](../getting-started/studio.md)。

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

[鉴权](authentication.md) · [运维与恢复](operations.md) · [配置参考](../reference/configuration.md) · [插件管理](plugin-management.md)

源码：[HTTP 服务](../../../axonx/components/service/http/service.py)、[Studio 目录发现](../../../axonx/components/service/http/studio.py)、[TaskManager 关闭](../../../axonx/components/task_manager/local/manager.py)。
