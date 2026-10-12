# 服务自更新

通过 `axonx start` 启动的服务可以使用经过认证的 Job 更新后端和 Studio。在 Studio 中，选择目标机器，打开 **运行 → 环境 → 服务更新与重启**。使用前配置服务 token；未认证服务不会暴露更新 Job。

## 选择更新方式

Studio 默认选择 **源码仓库 · origin/main**。通过 pip 安装的服务应选择发布包更新方式。

```bash
# 丢弃本地源码改动，将启动目录所在仓库切换到 origin/main
axonx update_from_git

# 在服务的 Python 环境中更新最新稳定发布包
axonx update_from_pip

# 显式取消正在运行的受管理 Run
axonx update_from_git --force true
```

连接目标和凭据沿用普通 Job 的客户端选项。更新作用于所选服务机器，而不是客户端机器。

Git 方式要求服务从原启动目录所在仓库加载 AxonX，并已安装 Git 及 Studio 支持的 Node.js/npm。先获取 `origin/main`，再丢弃受版本控制的源码改动、清理未跟踪的源码文件，将本地 `main` 分支对齐获取到的 commit。保留忽略文件，包括常见的 `.env`、`.venv` 和 `.axonx/`；配置的 workspace、日志目录、Python 环境、加载的 `.env` 文件和未跟踪的启动配置文件（包括继承的配置）也会加入清理排除项。运行路径与受版本控制的源码或仓库根目录重叠时会被拒绝；破坏性操作前会同时检查当前源码和获取到的 commit。原启动子目录必须存在于获取到的 commit 中。通过 `npm ci`、`npm run build` 构建 Studio，然后从仓库以 editable 模式安装后端和 Studio。

pip 方式使用服务解释器执行 `-m pip install --upgrade axonx axonx-studio`。Studio 的 Python 包包含静态资源，因此不需要 npm 构建。源码安装、导入路径遮蔽已安装包的情况（包括 `PYTHONPATH`）会被拒绝；源码安装使用 Git 更新。稳定版本选择遵循 pip 的常规升级行为。

服务应使用独立且可写的 Python 环境。自更新不会协调使用同一环境的其他独立进程，不会升级研究插件，也不保证独立发布的两个包版本兼容。

## 不更新，仅重启

在 Studio 中选择 **仅重启服务**，或执行：

```bash
axonx restart_service
# 显式取消正在运行的受管理 Run
axonx restart_service --force true
```

Studio 按所选服务实际配置的 Job 展示操作。仅重启的服务需要 `restart_service` 和 `get_update_status`，无需配置 Git 或 pip 更新 Job。

该 Job 需要认证，复用维护、关闭和进程替换流程。跳过 Git、npm、pip 安装及安装检查，使用原环境、工作目录和启动参数启动新的 Python 解释器，保留端口和 PID，重新从磁盘加载已安装的包及 editable 源码。此模式不要求 Git、Node.js 或已安装 Studio。默认本服务有受管理 worker 时拒绝重启；只有 `force=true` 成功停止它们后才继续，共享工作区中的外部 Run 不阻止重启。

重启记录使用 `mode: restart`，通过现有的 `get_update_status` Job 查询，阶段为 `accepted`、`starting`、`succeeded` 或 `failed`。仍需替换后的服务成功监听才记为成功。仅重启不会更新另一个服务的独立仓库或 Python 环境，也不会协调共用安装文件的其他服务。

## 接受请求和重启

默认本服务有受管理 worker Run 时拒绝更新或重启。共享工作区中由其他服务或 CLI 启动的 Run 不阻止本服务重启，也不会被取消。已发布终态但进程尚未退出的受管理 worker 仍需停止。共享源码或 Python 环境的 Git/pip 更新仍会影响其他服务，应协调部署。`force=true` 会在接受请求前取消精确的受管理 Run；无法确认终止的受管理 Run 会阻止更新。源码和环境预检查先于取消操作。接受请求后进入维护状态：拒绝新的本地 Job（`version` 和 `get_update_status` 除外）、插件环境变更和 Task 提交。

发起更新的 HTTP、SSE 或 MCP 响应发送完成后才开始关闭服务。Application 正常清理流、组件和子进程。关闭后的服务将自身替换为预先保存的纯标准库更新执行器，执行更新后使用同一解释器、原启动目录及原 `axonx start` 参数重新启动。整个过程保留进程 PID，也适用于 systemd 或 launchd 托管。自定义嵌入式 ASGI 应用不支持自动重启。

获取源码、构建、安装和重启期间服务不可用。Studio 在页面可见时每三秒重试查询状态，成功后提供“重新加载 Studio”。服务中断期间无法展示新的进度和日志。进程托管器需要允许更新耗时；每条外部命令的超时为 30 分钟，完成、超时或中断时都会清理该命令的进程组。

## 持久化结果和失败

更新 Job 返回成功仅表示请求已接受，不表示更新完成。保存 `answer.update_id`：

```bash
axonx get_update_status --update-id YOUR_UPDATE_ID
# 省略 ID 则查询最近一次更新
axonx get_update_status
```

响应包含 `record` 和最多 64 KiB 的日志尾部。记录包括更新方式、阶段、时间、更新前后包版本、获取到的 commit 和错误。状态及执行器快照保存在 `<workspace>/updates/<update_id>/`；保护这个目录，因为重启计划可能包含带凭据的启动参数。

阶段为 `accepted`、`fetching`、`cleaning`、`building`、`installing`、`verifying`、`starting`、`succeeded` 和 `failed`。只有替换后的 HTTP 服务开始监听，才记录成功。中断的记录会在后续服务启动时标记为失败。

构建、安装或验证失败会记录错误，并尝试重新启动服务。这是恢复可用性的尝试，不是回滚：Git 改动和 pip 的部分安装结果会保留。如果导入或启动失败导致服务无法记录错误，请在本地检查持久化记录和 `update.log`；后续启动会处理未完成记录。当前不提供自动版本回滚。

## MCP 传输

MCP 端点统一使用无状态 Streamable HTTP 和 JSON 响应。客户端不能依赖跨调用或跨重启保留的服务端会话。
