# 架构概述

AxonX 将能力调用、研究执行和结果存储分开。CLI、Studio 与外部 Agent 调用 Job；Job 的异步 Step 访问组件；耗时研究工作由同步 Task 在 worker 进程中执行。结果落到工作区后，任务查询和 Studio 使用同一批记录。

![AxonX 架构分层](../../figures/concepts/architecture.svg)

## 各层职责

| 层 | 负责什么 | 典型对象 |
| --- | --- | --- |
| 客户端 | 组织参数、凭据，消费 JSON 或事件 | CLI、Studio、HttpClient、McpClient |
| 协议 | HTTP、MCP、SSE、上传与 Bearer 鉴权 | HttpService |
| 编排 | 参数校验、执行异步步骤、形成 JobResponse | Dispatcher、Job、BaseStep |
| 组件 | 管理可复用能力和生命周期 | TaskManager、TaskRepository、Agent、Proxy |
| 任务 | 执行具体研究步骤，生成校验后的结果 | BaseTask 和插件 Task |
| 存储 | 保存状态、成功元数据、进度与研究产物 | 工作区和独立日志目录 |

HTTP 的普通调用与 SSE 事件调用经过相同 Job 能力层。MCP 把公开 Job 映射为工具，返回普通响应。SSE 是另一个 HTTP 入口，提供实时事件；两者不应作为同一种传输理解。

## 查询能力的执行链

以 `status` 为例：

1. 客户端提交 `task_id` 到 `/jobs/status`。
2. 协议校验服务凭据，Dispatcher 找到 Job 并验证参数。
3. Job 执行 `get_status` Step。
4. Step 从 TaskManager / Repository 查询记录。
5. 返回包含状态的 `JobResponse.answer`。

查询不会重新执行 Task。Repository 监听工作区记录变化，向调用者提供当前索引；观察文件变化和执行 worker 是不同职责。

## 研究能力的执行链

以 `submit --task demo` 为例：

1. `submit_task` Step 将结构化参数编码成 Task 命令参数。
2. 本机 TaskManager 校验任务定义与身份，创建 queued 记录，启动独立子进程。
3. Job 返回含 `task_id`、`run_id`、注册名的 TaskHandle。
4. worker 解析 typed input，顺序执行同步步骤并写进度、状态和日志。
5. 成功时构建 typed output，先写 `metadata.json`，再发布成功状态。
6. 客户端通过 `wait_task` 确认终态，通过文件或研究页面读取结果。

`axonx exec` 直接在当前 CLI 进程运行同一种 Task，不走 HTTP 或常驻 TaskManager。进程隔离方便取消和异常对账，并不等于代码安全沙箱。

## Application 装配

Application 根据配置与注册表创建 Component、Job 和 Scheduler。组件通过 `depend` 声明依赖，由应用按拓扑顺序启动；正常退出按依赖反序关闭，启动中失败会回滚已启动对象。

这意味着配置中的组件名称具有实际引用意义。例如 TaskManager 的 `task_repository: default` 绑定同名 Repository；同步组件也可依赖这份 Repository。把组件删掉却保留引用会导致启动失败，而不是自动采用其他后端。

常驻服务在 ASGI lifespan 中管理 Application。服务退出会进入关闭流程，TaskManager 停止它管理的 worker；文件保存了状态，但没有通用的断点续跑机制。

## 插件与 Agent 的位置

插件通过已安装 Python distribution 的入口点和 `plugin.yaml` 提供 Task、Component 和 Job。Task 类型及其输入输出 Schema 来自插件类，具体量化算法由插件实现。安装改变环境，贡献加载发生在应用装配时。

Agent 是组件能力之一，默认实现使用 Claude 后端。它能以配置的 Job 工具读取任务证据，也受到 SDK 工具、运行目录和权限模式影响。研究任务可以完全独立于 Agent 执行。

远程服务是另一个完整 Application，拥有自己的插件环境、worker 和工作区。Studio 的远程操作经本机后端转发，CLI 的显式 `--target` 则直接连接目标。

## 设计边界

- `source_tasks` 表示记录中的上游关系；框架不会据此自动执行整条 DAG。
- Repository 的索引可从记录重建，产物文件和插件环境必须另外保留。
- 同步复制终态 Task 目录，不迁移活跃 worker，也不复制整个工作区。
- 资源查询提供机器读数，不负责自动选机或 GPU 调度。

## 继续阅读

- [Job 与 Task](jobs-and-tasks.md)：两种执行抽象与选择原则。
- [工作区](workspace.md)：文件格式和恢复边界。
- [远程机器](../guides/remote-machines.md)：两条远程调用路径。
- [框架扩展](../development/framework-extensions.md)：组件与编排扩展。

实现入口：[Application](../../../axonx/core/application.py)、[TaskRunner](../../../axonx/task/runtime/runner.py)、[HTTP 装配](../../../axonx/components/service/http/app.py)。
