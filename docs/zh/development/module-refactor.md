# 八模块重构

Python 包已整理为八个职责独立的模块，删除旧内部导入路径和仅用于兼容的文件。Task ID、生命周期记录、产物和配置数据保持现有语义；Python 导入和执行接口、Job help 的使用说明字段按下文调整。

## 能力清单与调整

| 模块     | 拥有的能力                                                                                | 重构与精简                                                                   |
| -------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `app`    | 应用装配、组件、Job 和 Step、HTTP/MCP/SSE、Agent、服务侧 Repository、工作区操作、远端同步 | 整体归拢现有服务代码，保留内部结构；插件的应用装配留在这里。                 |
| `cli`    | 命令分发、本地 exec/plugin/start 命令、输出呈现                                           | 按所选命令导入子系统；共享 argv 解析独立于可执行入口。                       |
| `daemon` | 守护、所属子进程、本地控制协议、更新执行                                                  | 独立 worker 不导入应用；更新 worker 迁入进程所有者所在模块。                 |
| `cron`   | crontab 配置、解析、下次触发时间计算、触发                                                | 复用参数校验，通过注入启动回调解除对 daemon 的直接导入。                     |
| `config` | Provider、运行与连接模型、dotenv、配置定位、继承和合并                                    | 保留声明式模型；复用标量转换，删除 resolver 的历史转导出。                   |
| `task`   | Task 编写与组合、发现、执行、生命周期、产物、查询、副本处理、研究契约、内置能力           | 保留内部目录；拥有 Task 事件，复用参数解析，删除旧导入门面和无调用辅助函数。 |
| `plugin` | Manifest 与贡献数据、已安装插件发现、身份、wheel 构建、安装卸载、符号加载                 | 从 `plugin_kit` 改名；CLI 处理和应用装配迁回所属模块；统一产物准备逻辑。     |
| `common` | 文件机制、基础日志、通用参数转换和原始日志数据                                            | 不导入其他七个模块；领域实现和专用常量留在所属模块。                         |

`app` 可以依赖 `task`、`plugin`、`config`、`common` 和 daemon 控制协议；`task` 可以依赖 `plugin`、声明式 `config`、`common`；`plugin` 可以依赖声明式 `config` 模型和 `common`；`config`、`cron` 可以依赖 `common`，cron 还使用配置定位；`cli` 负责组合入口。daemon worker 保持为仅使用标准库的独立程序。包初始化不能提前导入无关子系统。

## 内部能力归属

- **App：** `core` 拥有装配、依赖顺序、上下文、调用分发；`components` 拥有 Agent 与会话存储、客户端、Job、代理、HTTP 服务、Repository、网络同步、更新请求；`steps` 暴露对应操作；`workspace` 拥有浏览、预览、删除、上传暂存。
- **CLI：** 分发到服务启动、独立 Task 执行、插件命令或远程 Job；输出层拥有启动横幅、JSON、流式呈现。完整解析归 CLI；远程网关启动 CLI 子进程，由命令入口拒绝启动服务和嵌套 target。
- **Daemon：** 本地客户端拥有启动和控制交换；独立守护拥有 worker 就绪、替换、回收、更新状态；独立更新 worker 拥有构建安装子进程及清理。
- **Cron：** 代码和 `.cron` 资源放在一起，保留解析、按名称定位、时区感知的下次触发计算、未来触发清理；通过注入回调交接进程启动。
- **Config：** 模型描述运行设置、组件、Job、目标机器和插件；应用与 Studio 校验由 App 拥有；resolver 拥有继承、环境变量展开、深度合并；locator 拥有显式路径、内置名称、已安装入口的定位。
- **Task：** 保留核心编写、身份、组合、发现、执行器与 runner、纯数据模型、元数据日志事件存储、输入模型与在线发布快照、关系图摘要跟随查询、有预算的展示副本、研究契约、事件回放、股票/Tushare/钉钉内置能力，均不依赖服务实现。
- **Plugin：** Provider 注册、Manifest 与贡献索引描述公开名称，发现与指纹描述安装包和 wheel 内容，产物准备、构建、安装卸载拥有包环境变更，符号加载只校验调用者传入的基类。
- **Common：** 标量与嵌套参数转换、原始日志数据、文件路径约束与原子写校验版本、基础进程日志、可安全取消的阻塞操作。这里不放服务、Task 启动、调度或插件安装策略。

## 执行顺序

1. 建立基线，保存序列化契约快照。
2. 迁移现有目录，同步 Python 导入、插件源码、打包和文档路径。
3. 将共享命令解析、Task 事件、注册机制和路径工具从服务实现中分离。
4. 删除仅用于兼容的文件、无调用函数，合并重复的参数解析与产物准备逻辑。
5. 验证允许的依赖、独立进程导入和真实 CLI 入口。
6. 执行受影响及全量 Python 测试、契约检查、打包冒烟、文档构建和针对改动文件的 pre-commit。

基线为 `PYTHONPATH=. python -m pytest -q`：**774 passed，2 deselected**。需要凭据或外部服务的集成测试不在本轮范围内。

## 完成证据

- 八个一级模块已落地，App/Task 内有意义的子目录继续保留；`plugin_kit` 和旧包路径已移除。
- 标量与 argv 解析、插件产物准备均复用统一实现；删除九个 Task 导入兼容门面、无调用的 Task argv 辅助函数、无调用的 Demo Job Step；Task、插件、HTTP 专用常量归回所属模块。
- 框架 Python 源码从 **231 个文件、17,768 行** 调整为 **228 个文件、17,262 行**，净减少 **506 行**。
- Python 全量回归：**760 passed，2 deselected**；旧兼容路径检查已替换为依赖与独立导入检查；真实 CLI exec 在不加载 App/FastAPI 的情况下完成。
- **51 个序列化模型**与重构前快照完全一致，Studio 契约生成检查通过。
- Studio：**275 项测试通过**，lint、格式检查、生产构建通过。
- 文档构建通过，验证 **124 篇指南、508 个本地链接和资源**，含双语导航、源码链接、导出文件。
- 核心包与三个研究插件的 wheel、sdist 构建及内容校验通过；四个 wheel 已在源码目录外的临时虚拟环境安装并验证，依赖复用现有环境（`--system-site-packages`、`--no-deps`）。
- 针对改动文件的 pre-commit 通过，含 Python 检查、文档格式、Studio 契约；未执行依赖凭据的集成测试、付费模型调用或远程部署。

## Common 归属精简

第二轮不保留旧 Common 路径或转导出。Common 最多保留两级目录：文件机制集中在 `fs/`，`logging.py`、`logs.py`、`async_work.py`、`arguments.py` 和 `constants.py` 直接归 Common，删除笼统的 `utils/` 转导出层：

| 能力                                               | 所属位置                                                                         |
| -------------------------------------------------- | -------------------------------------------------------------------------------- |
| Task 状态、类型、分类枚举与 Run 日志作用域         | `task/enums.py`、`task/runtime/logging.py`                                       |
| 组件类型、应用和 Studio 模型、构建诊断、日志保留   | `app/components/types.py`、`app/config.py`、`app/core/`                          |
| Provider 声明和注册表                              | `plugin/registry.py`，只接收普通分类字符串                                       |
| 连接参数与地址规则、环境文件、执行环境协议、默认值 | `config/target.py`、`config/env.py`、`config/execution.py`、`config/defaults.py` |
| CLI Command、argv 解析、使用说明                   | `cli/parser.py`、`cli/usage.py`                                                  |
| 根路径约束                                         | `common/fs/paths.py::ConfinedPaths`                                              |
| 上传命名和暂存策略                                 | `app/workspace/paths.py::WorkspacePaths`                                         |

`config.RuntimeConfig` 仅描述进程设置，`app.config.ApplicationConfig` 拥有服务和 Studio 校验，配置与插件导入不再需要 Task。Task API 为 `TaskExecutor.execute(name, inputs) -> TaskMetadata`；CLI 原始 argv 存放在 `Command.raw_arguments`，不再混入业务参数。Job help 响应不再携带 CLI 使用说明。删除无生产调用的 `file_versions` 及其独立测试。Task 身份、生命周期和产物格式，以及 51 个序列化模型均保持一致。

Common 从 **26 个 Python 文件、1,309 行**收缩到 **13 个文件、518 行**，减少 **791 行**。全量回归通过 **760 项测试**，包含目录依赖约束、独立导入、新执行接口、日志清理和真实远程 CLI 转发。删除的测试只覆盖已移除的兼容路径或无调用接口；新的模块边界和执行结果检查替代原有约束。
