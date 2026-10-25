# 架构概述

AxonX 将能力调用、研究执行和结果存储分开。CLI、Studio 与外部 Agent 调用 Job；Job 的异步 Step 访问组件；研究工作由同步 Task 在独立 CLI 进程中执行。结果落到工作区后，任务查询和 Studio 使用同一批记录。

![AxonX 架构分层](../../figures/concepts/architecture.svg)

## Python 模块边界

Python 包有七个一级模块，`app`、`task` 内已有且有意义的子目录继续保留。

| 模块     | 职责                                                                                     |
| -------- | ---------------------------------------------------------------------------------------- |
| `app`    | 服务配置、应用装配、Component、Job/Step、HTTP/MCP、Agent、服务侧 Repository 与工作区操作 |
| `cli`    | 可执行入口、命令路由、本地命令与输出                                                     |
| `daemon` | 独立守护、本地控制、所属更新子进程                                                       |
| `cron`   | crontab 代码与配置，通过注入回调启动命令                                                 |
| `task`   | 独立 Task 执行、记录、研究契约、产物与副本处理                                           |
| `plugin` | Task manifest、发现、wheel 构建、安装卸载                                                |
| `common` | 通用配置加载、环境/运行/连接数据、注册、进程身份、文件、日志与异步机制                   |

依赖从调用者指向能力所有者：`app` 使用 `task` 数据接口与 `common`，`task` 使用 `plugin` 与 Common 机制，`plugin` 使用 Common 机制；`common` 不导入这些子系统。CLI 在服务及远程调用时导入 App，本地 exec/kill 与 cron worker 不加载 App；服务配置模型和 YAML 归 `app/config/`，通用加载机制归 `common`，cron 不导入 daemon，daemon worker 保持为仅使用标准库的独立程序。参见[重构计划与验证](../development/module-refactor.md)。

## 各层职责

HTTP 的普通调用与 SSE 事件调用经过相同 Job 能力层。MCP 把公开 Job 映射为工具，返回普通响应。SSE 是另一个 HTTP 入口，提供实时事件；两者不应作为同一种传输理解。

## 查询能力的执行链

以 `status` 为例：

CLI 或 Studio → Job → 查询 Step → Repository → 已发布的 `metadata.json`。

查询不会重新执行 Task。Repository 监听工作区记录变化，向调用者提供当前索引；观察文件变化和执行 worker 是不同职责。

## 研究能力的执行链

以 `axonx exec --task demo` 为例：

CLI → `TaskExecutor` → `TaskRunner` → 同步 Task 步骤 → 原子发布生命周期记录和产物。Task 进度事件由 Task schema 拥有，Job 层复用它们作为传输数据。

## Application 装配

Application 根据配置与注册表创建 Component 和 Job。组件通过 `depend` 声明依赖，由应用按拓扑顺序启动；正常退出按依赖反序关闭，启动中失败会回滚已启动对象。daemon 分别启动服务和 cron worker，cron 通过启动回调请求独立的 exec 进程。

## 插件与 Agent 的位置

安装只修改选定 Python 环境，不刷新服务已加载模块，也不追踪待重启状态。新的 CLI 进程加载已安装环境；需要重新加载 Task schema、Component 或 Job 时重启常驻服务。已有进程不提供版本隔离，插件环境修改不再串行协调。

AxonX 提供量化研究 Harness：Task 契约、执行、记录和产物查询。模型／工具循环与会话上下文由外部 Agent 宿主或内置 Claude Agent SDK 后端管理。具备 Skill 或开发指南、源码访问及代码工具时，两条 Agent 路径均可开发插件，并以 Task 证据驱动迭代。内置 Agent 是组件能力之一，实际能力取决于 Job 工具、SDK 工具、运行目录和权限模式。研究任务可独立于 Agent 执行。

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

实现入口：[Application](../../../axonx/app/core/application.py)、[TaskRunner](../../../axonx/task/runtime/runner.py)、[HTTP 装配](../../../axonx/app/components/service/http/app.py)。

App 不导入研究插件，只读取 Task 契约与工作区数据，并触发本机进程校验。Task 定义通过 CLI 子进程查询。通用注册和进程机制归 Common，Task 生命周期策略归 Task。见[模块重构](../development/module-refactor.md)。
