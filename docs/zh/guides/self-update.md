# 服务更新与重启

Daemon 启动的服务提供认证更新 Job，操作时保持启动解释器、工作目录和配置一致。

## 选择更新方式

```bash
axonx update_from_git
axonx update_from_pip
axonx restart_service
```

选择其中一种操作。Git 模式要求运行源码属于启动仓库并具备 git/npm，快进当前分支、构建 Studio、重装源码包。Pip 模式升级 axonx 和 axonx-studio，拒绝源码/editable 遮蔽。Restart 不修改包，用原启动参数/环境重载应用。这些 Job 不接受 force 参数。

## 远程更新

本地修改、提交并 push 代码后，在本地执行，将示例地址替换为目标服务地址：

```bash
# 提前配置 AXONX_TARGET_TOKEN 为目标服务的 token
axonx update_from_git --target axonx.example.com:1024

# 服务恢复后查看更新结果
axonx get_update_status --target axonx.example.com:1024
```

远程会执行：停止应用服务 → `git pull --ff-only` → 构建 Studio → 重装 AxonX 和 Studio → 校验依赖及导入 → 启动新服务。

## 准入与响应边界

更新器预留 maintenance，准备持久化记录，在触发的 HTTP/MCP 响应发送完成后提交。维护期间除 version、get_update_status 外拒绝新本地 Job。准备失败释放准入，接受操作不代表完成。

Daemon 停止并替换应用服务，服务拥有的手动 CLI 进程随服务停止，Daemon 定时命令继续。活动定时工作期间更新源码/依赖需自行协调，运行进程不固定代码版本。Daemon 作为监督进程保留，服务进程被替换。

## 持久化结果与失败

保存返回的 update_id，服务恢复后查询：

```bash
axonx get_update_status --update-id ACTUAL_UPDATE_ID
axonx get_update_status
```

记录和 update.log 位于服务工作区的 Daemon 身份目录：`daemon/<identity>/updates/<update_id>/`。阶段包括 accepted、fetching、building、installing、verifying、starting、succeeded、failed。替换服务报告 ready 后才记录成功，状态响应返回记录和最多 64 KiB 日志。

构建/安装/重启期间服务可能不可用。失败被记录，Daemon 尝试重新启动服务，但不会回滚部分 Git/pip 变更。导入失败导致 API 无法恢复时检查本地 Daemon/服务日志。后续 Daemon 启动把未结束的更新标记失败。嵌入式应用需显式宿主更新后端和响应完成边界。

源码：[更新器](../../../axonx/app/components/updater/local.py)、[Daemon 控制](../../../axonx/daemon/client.py)、[监督器](../../../axonx/daemon/supervisor.py)。
