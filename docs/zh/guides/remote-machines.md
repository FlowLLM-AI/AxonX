# 远程机器

## 准备目标服务

在目标设置 AXONX_SERVICE_TOKEN 后运行 `axonx app --service.host 0.0.0.0 --service.port 1024`。确认网络、解释器、工作区、插件依赖和输入文件。显式 CLI target 直接连接，原生命令要求目标暴露认证 cli 能力。

## CLI 直连

```bash
export AXONX_TARGET_TOKEN='replace-with-target-token'
axonx version --target node-b:1024
axonx plugin list --target node-b:1024
axonx exec --task demo --task-name remote-check --x 1 --y 2 --target node-b:1024
axonx status --task-id 'base#demo#remote-check' --detail full --target node-b:1024
```

普通 Job 直接调用目标，原生命令通过 cli 转发 argv。Exec 等待完成、传输目标 stdout/stderr 并保留退出码。保留 target、Task ID、started_at 以继续观察。连接取消可能停止所拥有的远程执行，重试前先检查记录。

## Studio 后端转发

在本地服务 targets 列表配置目标地址和 token，Studio 选中机器并发送传输层 target，由后端读取凭据。业务参数不能覆盖路由凭据，各目标状态和 Agent 会话独立。

## 远程文件与插件

原生命令路径均在目标服务工作区解释，包括 plugin install/build/inspect 的源码路径。--target 不上传本地文件。本地构建 wheel、上传 /upload、安装返回的绝对 location、清理相对 path，再重启常驻服务刷新 Task 目录，详见[插件部署](../plugins/management.md)。

## 连通性、资源与停止

list_machines/machine_status/diagnose 提供观察到的资源，不自动调度机器。Kill 使用 metadata 的源 execution_target 和 workspace_dir。展示副本不能控制源进程，machine_id 也不是地址。

[认证](authentication.md) · [部署](deployment.md) · [任务管理](task-management.md)
