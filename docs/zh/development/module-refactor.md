# 模块边界与执行状态重构

收敛为七个一级目录，App/Task 内有意义的子目录继续使用。本轮主动删除兼容路径和隐式能力。

| 模块   | 职责                                                                                                                            |
| ------ | ------------------------------------------------------------------------------------------------------------------------------- |
| app    | 服务配置与装配、组件生命周期、Job/Agent、HTTP/MCP/SSE、工作区、Task 观察与订阅                                                  |
| cli    | start、exec、kill、Task 定义和 plugin 命令，以及显式远程转发                                                                    |
| daemon | 服务/cron 守护、已启动子进程的回收与更新 worker                                                                                 |
| cron   | 配置解析、未来触发，通过注入回调交接进程启动                                                                                    |
| task   | Task 编写、执行、纯数据契约、存储、查询、状态校验与修正、同步产物                                                               |
| plugin | Task-only manifest、发现、构建、校验、安装和卸载                                                                                |
| common | 通用配置加载、环境/运行/连接数据、Provider 注册、机器/进程身份、精确进程信号与等待、文件锁/原子写、基础日志、参数转换和异步清理 |

## 破坏式调整

- 将共享 Workspace 的文件操作、格式预览和结果模型集中到 `common/workspace/{core,preview,models}.py`。包入口只导出 `Workspace`，不加载 Pydantic，结果模型从 `.models` 显式导入。删除旧平铺预览模块与 `app/workspace/`；App 适配和 Task 策略仍由各自模块持有。
- 将 `axonx/config/` 与 `app/config.py` 合并到 `app/config/`，统一 App 模型、resolver 与内置 YAML。通用 `ConfigLoader`、dotenv、文件/entry-point 定位、运行和连接数据归 Common；CLI 输出选项归 `cli/options.py`。删除旧导入路径。独立 exec/kill 只读环境和默认值；cron worker 经 Common 读取 YAML 后即可运行，不加载 App。
- 删除 `app/core/plugin_runtime.py`、`app/steps/plugin/` 和四个插件管理 Job。删除启动时 `plugins.sources` 安装、`PluginConfig`、插件 Components/Jobs 贡献和旧 staged-install 旁路。
- App 不导入 `plugin`、Task builtins/runtime/catalog。Task 定义接口通过 CLI 子进程保持 JSON 边界，独立进程加载当前安装环境。
- Provider 装配是通用机制，迁至 `common/registry.py`；进程身份和信号机制迁至 `common/process.py`，不保留旧转导出。App 自定义服务能力通过 `Application(providers=...)` 和组件/Job 配置装配。
- `task/__init__.py` 按需导出，不提前导入可执行 Tasks。元数据增量扫描归 `task/storage/index.py`，祖先和关系上下文归 `task/query/context.py`；App 只负责轮询、缓存、调用和传输。
- 删除 `queued`。metadata 必须有机器 ID、正整数 PID 和带时区的进程创建时间；首份执行记录直接为 `running`。展示副本保留来源进程身份，通过 replica 标记禁止本机操作。
- `task/storage/records.py` 统一本机进程校验、失败收敛、覆盖冲突提示和显式 kill。启动/轮询检查未变化的运行记录；外机、副本和权限未知不回写。
- 新 Run 发布和状态修正使用短事务锁，运行期间不持锁；重跑打印 `Overwrite` 并保留 `persistent/`。kill 绑定 Run ID，默认 SIGTERM，强制信号必须显式指定。

## 验证范围

执行 Python 重点与全量测试、真实子进程和 CLI/HTTP 验证、独立导入边界检查；同步 Studio 类型与界面状态，执行测试、lint、格式和构建；验证双语文档、wheel/sdist 和源码目录外安装，最后执行改动文件的 pre-commit。凭据相关集成、付费模型和远程部署不在本轮范围内。

详细状态语义见 [Task 生命周期](../concepts/task-lifecycle.md)。

## 完成证据

- Python 全量：794 passed、2 deselected；覆盖真实进程终止、超时与强制重试、PID 复用、新 Run 保护、外机与副本拒绝操作、周期复核及远程 CLI。
- Studio：275 项测试通过，lint、格式与生产构建通过；Python/TypeScript 契约同步。
- 双语文档构建与改动文件 pre-commit 通过。
- 核心、Studio、三个研究插件的 wheel/sdist 构建完成；分发内容逐项核对，旧模块未混入。五个 wheel 在源码目录外的临时虚拟环境安装验证，复用现有依赖（system-site-packages、no-deps）。
- 安装后验证 exec、Overwrite/persistent 保留、定义查询、精确 kill、无插件导入的 App 观察与 Studio HTTP 静态资源。
- 未执行需凭据的集成测试、付费模型或远程部署。
