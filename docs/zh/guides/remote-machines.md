# 远程机器使用

AxonX 可以调用另一台机器上的服务。任务在被调用服务的 Python 环境中执行，使用该服务的插件、工作区和日志目录。CLI 显式直连与 Studio 后端转发需要分别配置凭据。

![远程调用路径](../../figures/guides/remote-machines.svg)

## 准备目标服务

目标机器安装 AxonX、需要的研究插件和模型依赖，配置独立服务 token，再启动服务：

```bash
export AXONX_SERVICE_TOKEN='<目标服务 token>'
axonx start --service.host 0.0.0.0 --service.port 1024
```

访问目标的 HTTP(S) 地址必须对客户端可达。内置 Uvicorn 服务不负责 TLS，跨网络部署可在外部终止 HTTPS，见[部署指南](deployment.md)。

## CLI 直连

```bash
export AXONX_TARGET_TOKEN='<目标服务 token>'
axonx version --target 'http://research.example:1024'
axonx get_task_definition --task demo --target 'http://research.example:1024'
axonx submit --task demo --x 1 --y 2 --target 'http://research.example:1024'
```

这里的域名为占位示例，需要替换。CLI 直接连接目标，不要求先启动本机 AxonX 服务，也不要求将它加入本机 targets。

当显式指定 `--target` 时，CLI 默认从 `AXONX_TARGET_TOKEN` 读取凭据；未指定时默认连接本机服务，读取 `AXONX_SERVICE_TOKEN`。`--token` 可覆盖环境来源。

等待、查状态和读日志时必须继续选择同一目标。TaskHandle 没有把远程地址变成自动路由信息，应在脚本或实验记录里同时保留目标地址。

## Studio 后端转发

Studio 请求自己的同源后端，浏览器保存本机服务 token。后端根据请求中的 target 选择预先配置的远程凭据。

本机配置 `remote.yaml` 示例：

```yaml
extends: default
service:
  host: 127.0.0.1
  token: ${AXONX_SERVICE_TOKEN}
targets:
  - address: http://research.example:1024
    token: ${AXONX_REMOTE_RESEARCH_TOKEN}
```

```bash
export AXONX_SERVICE_TOKEN='<本机服务 token>'
export AXONX_REMOTE_RESEARCH_TOKEN='<目标服务 token>'
axonx start --config remote.yaml
```

重启后在 Studio 机器入口选择目标。远程 token 留在服务端配置，浏览器不需要直接保存它。

地址会规范化，targets 不允许重复地址。转发目标未配置时会失败；UI 中能选择的目标应与本机配置一致。改配置后需要重启当前服务。

## 连通性与资源

```bash
axonx list_machines
axonx machine_status --target 'http://research.example:1024'
```

`list_machines` 由当前服务检查其 targets。CLI 直接查询目标的 `machine_status`，则在目标返回资源信息。

CPU、内存和 GPU 字段是查询时的读数，GPU 探测不可用时应查看返回字段，不能推断机器绝对没有 GPU。它们不提供资源预留、GPU 绑定或自动选机。

Studio 的 Machine resources 页面把同一类返回值展示为 CPU、内存和 GPU 卡片。下面是英文界面的资源区域截图，已去除机器地址；读数与设备数量属于截图时的示例机器，不是 AxonX 的部署要求。

![Studio 英文机器资源页面中的 CPU 内存与 GPU 读数](../../figures/studio/machine-resources.png)

## 远程文件和插件

本机安装的插件不会自动出现在远程。安装到目标可使用：

```bash
axonx plugin list --target 'http://research.example:1024'
axonx plugin install ./plugins/a158 --target 'http://research.example:1024'
```

安装后按返回的 restart_required 重启目标服务，再查询 Task 定义。远程 worker 运行该环境中的代码，source_tasks 也只定位目标工作区内目录。

需要复用本机上游产物时，应先传输需要的任务快照或按部署方式复制数据。原始数据、Agent 会话和模型环境不随远程调用迁移。

## 常见故障

| 现象                  | 判断与处理                                             |
| --------------------- | ------------------------------------------------------ |
| 连接拒绝              | 检查目标进程、监听 host/port、网络入口                 |
| 401                   | 直连核对目标 token；Studio 同时核对本机和 targets 凭据 |
| 目标未配置            | 把规范化地址加入本机 targets 并重启                    |
| Task 注册名不存在     | 检查目标插件安装与重启，勿只查本机环境                 |
| Schema 或返回字段不同 | 比较双方 version 和插件版本                            |
| 目标任务没有上游文件  | 先确认数据和 Task 目录已传到目标                       |

[鉴权](authentication.md) · [插件管理](plugin-management.md) · [Task 同步](task-sync.md) · [机器 API](../api/machines.md)

源码：[targets 模型](../../../axonx/config/models.py)、[远程客户端](../../../axonx/components/client/base.py)、[Job 路由](../../../axonx/components/service/http/jobs.py)。
