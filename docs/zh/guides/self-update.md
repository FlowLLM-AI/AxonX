# 服务更新与重启

`axonx start --config default --cron research` 启动稳定的 daemon，以及独立的 HTTP、cron worker。cron 请求 daemon 创建本地 exec 进程；替换 HTTP 和 cron 时，这些 Task 继续运行。daemon 不读取或改写 Task metadata。

在 Studio 所选机器的 **系统管理 → 运行环境 → 更新或重启服务** 中操作。更新要求鉴权及相应更新／状态 Job；嵌入式 ASGI 应用不提供进程守护。

## 原地更新

```bash
axonx update_from_git
axonx update_from_pip
axonx restart_service
```

连接参数选择执行操作的服务机器。Git 更新在启动仓库的当前分支和 upstream 上执行 `git pull --ff-only`，不重置分支、不清理未跟踪文件；分支分叉或本地修改冲突时更新失败。需要安装 Git 和 Node.js/npm。随后通过 `npm ci`、`npm run build` 构建 Studio，并从该仓库以 editable 模式安装后端与 Studio。

Pip 更新使用服务解释器执行 `-m pip install --upgrade axonx axonx-studio`。源码安装或源码遮蔽已安装包时必须使用 Git 更新。插件不自动升级。“仅重启”跳过 Git、npm 和 pip。

源码、包和依赖都在原位置更新，不复制 release，也不提供版本隔离环境。运行中的 Task 不会收到终止信号，但后续 import、子进程和文件读取可能看到更新后的代码或依赖。

## 进程归属

发起操作的 HTTP、SSE 或 MCP 响应完成后，daemon 才执行更新。先停止 cron 的新触发，已有 exec 子进程继续运行。更新执行器作为临时子进程运行；构建、安装期间 HTTP 仍可查询更新状态。之后 daemon 关闭并替换 HTTP，再按原启动参数和目录启动新的 cron worker。

只有新 HTTP 开始监听，且配置的 cron worker 就绪，才记录成功。daemon PID 保持不变，HTTP 和 cron PID 改变。worker 异常退出后退避重启；Task 退出后只回收进程、记录退出码，不自动重试或重跑。

Studio 可见时每三秒查询状态，HTTP 替换期间自动重连。外部构建／安装命令有 30 分钟超时，在结束、超时或中断时清理各自的进程组。

## 状态与失败

```bash
axonx get_update_status
axonx get_update_status --update-id YOUR_UPDATE_ID
```

更新响应成功只表示已接受，保存 `answer.update_id` 并等待最终记录。记录和执行器快照位于 `<workspace>/daemon/<instance>/updates/<update_id>/`，instance 区分主机、绑定地址、端口及启动目录。`get_update_status` 返回记录和最多 64 KiB 日志尾部，不读取旧的未分域记录。

阶段为 `accepted`、`fetching`、`building`、`installing`、`verifying`、`starting`、`succeeded`、`failed`。构建、安装失败及更新器异常退出保持 failed，同时 daemon 尝试恢复 worker。部分源码或包变更会保留，不自动回滚。daemon 重启时将中断的更新标记失败，不自动续跑。

## Daemon 生命周期

`axonx start` 保持前台运行，可由外部进程管理器托管。启动时将纯标准库 daemon 脚本复制到私有 runtime 目录，不导入应用代码；普通服务更新不替换该进程。同一实例使用锁防止重复启动。worker 的 stdout/stderr 写入该目录的 `service.log`、`cron.log`，普通应用和 Task 日志仍使用配置路径。

Ctrl+C 或 SIGTERM 关闭 HTTP、cron 及正在执行的 updater，再退出 daemon；已有 cron exec 继续运行，后来的 daemon 不接管或重跑它们，完成状态仍由 Runner 发布。操作系统进程管理策略或关机可能终止这些进程；应用内重启不会停止外层服务 unit。
