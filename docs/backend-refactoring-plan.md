# AxonX 后端重构方案

> 状态：实施中（阶段 0 至阶段 5 已完成）
> 范围：`axonx/` 及与后端强相关的内置插件、测试和配置
> 原则：保持外部行为兼容，采用小步迁移，不进行一次性重写

## 1. 文档目标

本文档用于指导 AxonX 后端的系统性重构，重点解决以下问题：

- 通用运行时与 Alpha158、Tushare 等原生量化业务缺少清晰的内部边界。
- 部分模块职责过多，代码阅读和修改成本较高。
- Task 通过非结构化字典传递大量中间状态。
- 文件写入、摘要计算、Artifact 元数据生成等逻辑存在重复。
- HTTP、MCP、插件、进程管理等基础设施边界不够清晰。
- 全局 Registry 缺少应用级隔离会增加测试污染和插件冲突风险。

重构完成后，应达到以下目标：

1. 通用框架层只负责应用、组件、Job、Task、插件和传输层运行时。
2. Alpha158 和 Tushare 保持 `axonx` 原生能力，通过内部模块边界独立演进，不迁移为插件。
3. 高层模块负责流程编排，底层模块负责单一能力。
4. 重复的基础能力只有一个权威实现。
5. 公开 CLI、HTTP、MCP、配置和 Artifact 契约在迁移过程中保持兼容。
6. 每个重构阶段都能独立测试、审查和回滚。

## 2. 当前系统概览

当前 `axonx` 后端约 9,000 行 Python，主要由以下部分组成：

| 区域 | 当前职责 | 主要问题 |
| --- | --- | --- |
| `application.py` | 配置、插件发现、组件构建、生命周期、Job 分发 | 应用组装与运行逻辑集中在一个类中 |
| `components/` | 组件基类、注册表、客户端、Job、服务、插件、TaskManager | 抽象层和具体基础设施混合 |
| `task/` | 同步 Task、执行器、状态上报、业务任务 | 通用运行时与量化业务混合 |
| `task/alpha158/` | ETL、训练、预测、因子分析、回测 | 文件较大，依赖字符串键共享上下文，输出逻辑重复 |
| `task/data/` | Tushare 下载任务 | 原生数据业务与通用 Task 运行时边界不清晰 |
| `steps/` | Job Step 与 Workspace 操作 | 部分 Step 文件同时承担领域服务和协议适配 |
| `components/service/http.py` | REST、MCP、插件上传、静态站点 | 传输层职责过多 |
| `components/task_manager/local/` | 本地 TaskManager 门面及其进程、状态、日志和持久化服务 | 已按单一职责拆分，后续重点是稳定接口与并发回归 |
| `plugin/` | wheel 构建、检查、安装、Manifest | 构建、安装、发现、状态管理边界不清晰 |

现有架构中值得保留的基础包括：

- Pydantic 配置和 Schema。
- Component、Job、Task 的基础抽象。
- 应用级 Registry 副本。
- 组件依赖拓扑排序和反向关闭。
- Task 状态快照与独立 worker 进程。
- 插件 Manifest 和贡献注册机制。
- 已有的单元测试与集成测试。

因此，本次重构应以整理边界和降低耦合为主，而不是重新设计所有概念。

## 3. 重构原则

### 3.1 保持行为，分离结构

重构提交默认不得同时修改：

- 业务公式；
- HTTP 返回结构；
- CLI 参数格式；
- Job 名称；
- Task 名称；
- Artifact 文件名和 metadata schema；
- 默认配置语义。

如果确实需要修改外部契约，应独立提交，并提供迁移说明和兼容期。

### 3.2 组合优先于继承

只有在生命周期模板稳定且多个实现确实共享相同行为时才使用基类。文件存储、状态持久化、进程管理、Artifact 发布等能力优先通过组合对象复用。

### 3.3 不创建万能工具模块

公共代码按照能力组织：

```text
utils/fs/atomic.py        原子写入
utils/fs/checksum.py      摘要计算
steps/workspace/paths.py  Workspace 路径安全
```

避免继续向 `utils.py` 或 `helpers.py` 堆积无关函数。

### 3.4 I/O 边界显式化

网络、磁盘、子进程、环境变量和动态 import 都属于基础设施。业务计算模块不应直接操作这些能力，而应通过明确的服务或接口调用。

### 3.5 小步迁移

每个阶段遵循以下流程：

1. 为当前行为补充测试。
2. 引入新模块和新实现。
3. 让旧入口委托给新实现。
4. 验证兼容性。
5. 删除已经没有调用方的旧实现。

## 4. 目标架构

建议的目标目录如下。目录名可在实施时小幅调整，但模块边界应保持。

```text
axonx/
├── core/
│   ├── application.py       # 对外应用门面
│   ├── builder.py           # 根据配置构建应用图
│   ├── context.py           # 应用级上下文
│   ├── dispatch.py          # Job 校验、路由与远程分发
│   └── lifecycle.py         # 启动、回滚、关闭
├── components/
│   ├── base.py
│   ├── dependency.py
│   ├── graph.py
│   ├── registry.py
│   └── service/
│       └── http/
│           ├── __init__.py      # HttpService 兼容入口
│           ├── app.py
│           ├── jobs.py
│           ├── plugins.py
│           ├── mcp.py
│           └── static.py
├── jobs/
│   ├── base.py
│   ├── simple.py
│   ├── cron.py
│   └── proxy.py
├── tasks/
│   ├── base.py
│   ├── executor.py
│   ├── runner.py
│   ├── status.py
│   ├── reporting.py
│   ├── local/
│   │   ├── manager.py
│   │   ├── process.py
│   │   ├── repository.py
│   │   ├── reconciliation.py
│   │   └── logs.py
│   ├── alpha158/            # 原生 Alpha158 业务能力
│   │   ├── tasks/
│   │   ├── pipeline/
│   │   ├── artifacts/
│   │   └── domain/
│   └── data/               # 原生数据接入任务
│       └── tushare.py
├── transport/
│   └── client/
├── plugins/
│   ├── artifacts.py
│   ├── discovery.py
│   ├── installer.py
│   ├── repository.py
│   └── service.py
├── steps/
│   └── workspace/
│       ├── browser.py       # 浏览、预览、删除 Step
│       ├── task_graph.py    # 任务关系图 Step
│       ├── paths.py
│       ├── files.py         # 列表与删除服务
│       ├── preview.py
│       └── lineage.py
├── utils/
│   └── fs/
│       ├── atomic.py
│       └── checksum.py
├── config/
├── schema/
├── cli.py
└── __init__.py
```

依赖方向应保持单向：

```text
CLI / HTTP / MCP
        ↓
应用用例与服务
        ↓
Job / Task 运行时
        ↓
抽象协议与领域模型
        ↓
文件、网络、子进程、插件等适配器
```

通用运行时模块不得反向 import Alpha158 或 Tushare；原生业务模块可以依赖通用运行时和公共基础能力。

## 5. 重点模块设计

## 5.1 Application 拆分

当前 `Application` 同时处理构建和运行。目标设计如下：

### `ApplicationBuilder`

职责：

- 接收已经验证的 `ApplicationConfig`。
- 创建应用级 Registry 副本。
- 发现插件贡献。
- 实例化组件和 Job。
- 构建 `ComponentGraph`。
- 返回完整的 `ApplicationContext`。

构建期间产生的磁盘、插件安装等副作用应显式发生，避免隐藏在普通属性访问中。

### `ComponentGraph`

职责：

- 收集组件节点。
- 验证必需依赖是否存在。
- 检测循环依赖。
- 返回稳定的启动顺序。
- 提供能够定位具体依赖边的错误信息。

### `Application` 生命周期

职责：

- 按顺序启动组件。
- 记录已成功启动的对象。
- 启动失败时反向回滚。
- 关闭时聚合异常。
- 明确管理后台任务的所有权。

### `JobDispatcher`

职责：

- 查找 Job。
- 检查 Job 是否可直接调用或远程调用。
- 校验参数。
- 选择本地执行或远程客户端。
- 统一调用日志。

### 兼容策略

保留现有调用方式：

```python
app = Application(**config)
async with app:
    response = await app.run_job("demo")
```

`Application` 是生命周期边界，直接负责启动、回滚和关闭；构建、依赖排序与 Job 分发委托给对应对象。

## 5.2 Component 与 Registry

### 问题

- 构造函数大量接收无类型 `**kwargs`。
- Dependency 在启动期间由描述对象替换成实际组件。
- 内置 backend 使用 `@R.register(...)` 声明，注册表需要明确的复制与冻结边界。

### 方案

1. 为每类具体组件定义配置模型。
2. 将 Dependency 定义和解析逻辑移至 `components/dependency.py`。
3. Registry 只保存 provider 定义，不持有组件实例。
4. 保留 `@R.register(...)` 作为内置 backend 的统一声明方式。
5. 每个 Application 使用独立 Registry 副本。
6. 插件贡献只注册到当前 Application 的 Registry。
7. 根包完成内置模块加载后冻结模板 Registry，Application 只复制、不修改模板。

### 生命周期状态

可以将单一的 `is_started` 扩展成内部枚举：

```text
CREATED → STARTING → STARTED → CLOSING → CLOSED
                    ↘ FAILED
```

外部仍保留 `is_started` 属性，内部状态用于防止重复启动、启动中关闭和失败回滚等边界问题。

## 5.3 LocalTaskManager 拆分

目标组件如下：

### `TaskStatusRepository`

- 从 `status.json` 加载快照。
- 校验版本与 workspace。
- 原子保存。
- 返回深拷贝，避免外部修改内部状态。
- 将同步磁盘操作放入线程，避免阻塞事件循环。

### `TaskProcessSupervisor`

- 创建 worker 子进程。
- 保存 PID 与 Process 的关联。
- 收集有界 stderr tail。
- 管理 SIGTERM、等待宽限期和 SIGKILL。
- 回收进程与监控 Task。

### `TaskStateReconciler`

- 处理 worker 状态快照。
- 处理状态到达前进程已退出的情况。
- 处理 manager 重启后遗留的非终态任务。
- 保护终态，避免延迟快照覆盖取消或失败状态。

### `TaskLogLocator`

- 验证日志路径必须位于配置的日志目录。
- 为旧状态记录补全日志路径。
- 屏蔽路径逃逸。

### `LocalTaskManager`

只保留面向调用方的操作：

```python
submit(argv)
set_status(task_id, status)
get_status(task_id)
list_statuses()
cancel(task_id)
delete(task_ids)
```

所有状态变更应经过同一个 `asyncio.Lock` 或串行化命令入口，避免并发写入时产生不一致。

## 5.4 HTTP 与 MCP

### FastAPI 应用工厂

新增 `create_http_app(application, options)`，只负责：

- 创建 FastAPI。
- 安装 lifespan。
- 注册 Router。
- 挂载 MCP。
- 挂载可选的 Studio 静态资源。

### Router 拆分

| Router | 负责内容 |
| --- | --- |
| `jobs.py` | `/health`、`/jobs`、Job 调用 |
| `plugins.py` | 插件上传协议和 HTTP 错误映射 |
| `mcp.py` | 将可服务 Job 注册为 MCP Tool |
| `static.py` | 静态资源和 SPA fallback |

### 错误模型

内部服务抛出明确异常，例如：

```text
UnknownJobError
InvalidArgumentsError
RemoteExecutionDeniedError
PluginAuthenticationError
PluginArtifactError
```

HTTP 层负责将异常转换为状态码，核心逻辑不直接依赖 `HTTPException`。

## 5.5 插件系统

将插件能力分成四层：

1. `PluginArtifactInspector`：只读取 wheel 和 Manifest。
2. `PluginBuilder`：从源码构建 wheel。
3. `PluginInstaller`：安装依赖和 wheel。
4. `PluginRepository`：保存已安装插件状态和贡献索引。

`PluginService` 负责编排上述对象，并提供：

```python
prepare_source(path)
install_uploaded_wheel(data, filename, sha256)
list_plugins()
collect_contributions()
```

额外要求：

- `file_sha256` 使用公共实现。
- 所有状态文件使用公共原子 JSON 写入。
- 上传鉴权不能散落在安装器中。
- wheel 检查发生在安装前。
- 远程安装默认配置需要单独进行安全审查。

## 5.6 Workspace 服务

Workspace 功能分为三层：

### 路径策略

`WorkspacePathResolver` 统一完成：

- 将相对路径解析到 workspace。
- 拒绝绝对路径。
- 拒绝 `..` 路径逃逸。
- 校验根目录本身是否允许被操作。
- 处理符号链接策略。

### 读写服务

- `WorkspaceListingService`
- `WorkspacePreviewService`
- `WorkspaceMutationService`

### Step 适配

Step 只从 `RuntimeContext` 读取参数，调用服务并设置 Response，不再包含 CSV、Parquet 或文件删除的实现细节。

## 5.7 Alpha158 重构

Alpha158 是最大的一组业务代码，应在核心运行时稳定后处理。

### 目标分层

```text
axonx/tasks/alpha158/
├── tasks/                  # Task 入口与步骤编排
│   ├── etl.py
│   ├── train.py
│   ├── predict.py
│   ├── factor_analysis.py
│   └── backtest.py
├── pipeline/               # 管线用例
│   ├── etl.py
│   ├── training.py
│   ├── prediction.py
│   ├── analysis.py
│   └── backtest.py
├── domain/                 # 纯计算与领域定义
│   ├── features.py
│   ├── labels.py
│   ├── market_state.py
│   ├── portfolio.py
│   └── metrics.py
├── artifacts/
│   ├── models.py
│   ├── reader.py
│   └── writer.py
└── config.py
```

### Typed State

每条管线使用明确状态对象代替任意字典。例如：

```python
@dataclass
class TrainingState:
    source: DatasetArtifact | None = None
    frame: pl.DataFrame | None = None
    feature_names: tuple[str, ...] = ()
    tuning_train: pl.DataFrame | None = None
    validation: pl.DataFrame | None = None
    model: object | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    output: TrainingArtifacts | None = None
```

每个步骤应通过参数和返回值表达依赖；只有需要统一进度汇报的管线步骤才接收 state。

### ETL 拆分

`alpha158_etl.py` 建议按以下顺序拆分：

1. `MarketDataLoader`：加载行情和参考数据。
2. `MarketDataValidator`：列、类型、日期和唯一性校验。
3. `TradingPanelBuilder`：构建交易面板。
4. `MarketStateBuilder`：上市、停牌、涨跌停、ST 等状态。
5. `Alpha158FeatureCalculator`：基础和滚动特征。
6. `LabelCalculator`：未来收益、截面标准化和排序标签。
7. `IndexWeightAttacher`：指数权重。
8. `DatasetStatistics`：数据质量统计。
9. `DatasetPublisher`：输出和 metadata。

Polars 表达式应尽量保持为纯函数，输入 DataFrame/LazyFrame，返回新的 DataFrame/LazyFrame，不读写 `self.context`。

### Artifact 模型

训练、预测、因子分析和回测共享：

```python
@dataclass(frozen=True)
class ArtifactFile:
    relative_path: str
    size: int
    sha256: str

@dataclass(frozen=True)
class TaskArtifactManifest:
    schema_version: int
    task_name: str
    task_id: str
    task_type: str
    source: dict[str, object]
    artifacts: dict[str, ArtifactFile]
```

各 Task 只提供自己的业务 metadata，公共 Publisher 负责 header、完整性摘要和原子落盘。

### 保持原生集成

Alpha158 与 Tushare 是 `axonx` 的原生能力，不迁移到插件目录，也不通过插件 Manifest 注册。内部重构只调整模块职责，并遵守以下约束：

1. 保留现有 Task 名称、配置、CLI、Artifact 和公开导入契约。
2. 通用运行时不 import Alpha158 或 Tushare 的具体实现。
3. 量化依赖继续由主项目统一管理，不以插件拆包为目标。
4. 原生 Task 继续使用 `@R.register(...)` 声明，并通过 Registry 清单测试防止遗漏。
5. 模块移动时使用旧路径 re-export，并提供明确兼容期。

## 6. 公共基础能力

第一批适合抽取的公共能力如下：

### `utils.fs.atomic`

```python
atomic_write(path, writer)
atomic_write_text(path, content)
atomic_write_json(path, value)
```

要求：

- 临时文件与目标文件位于同一目录。
- 成功后使用 `os.replace`。
- 失败时清理临时文件。
- JSON 禁止输出 NaN 和 Infinity。

### `utils.fs.checksum`

```python
file_sha256(path)
directory_sha256(path, ignored_parts=...)
```

替代 Alpha158 和 Plugin 中重复的摘要实现。

### 错误类型

建立有限且有意义的错误层次，不要给每个函数创建异常类：

```text
AxonXError
├── ConfigurationError
├── ComponentGraphError
├── InvocationError
├── TaskRuntimeError
├── PluginError
└── ArtifactError
```

边界层可以捕获这些错误并映射为 CLI exit code 或 HTTP status code。

## 7. 分阶段实施计划

## 阶段 0：建立基线和保护网

目标：确定当前行为，避免把原有问题和重构回归混在一起。

步骤：

- [x] 记录当前工作区已有修改，重构不得覆盖无关改动。
- [x] 运行完整测试并记录失败基线。
- [x] 确认 CLI 主要命令已有输出与退出码测试。
- [x] 确认 HTTP Job、插件上传和 Workspace API 已有契约测试。
- [x] 确认组件启动、失败回滚、反向关闭已有测试。
- [x] 确认 TaskManager 正常退出、异常退出、取消、重启恢复已有测试。
- [x] 确认 Alpha158 已有固定小样本数据集和预期输出测试。
- [x] 保存 Artifact metadata、Schema、行数和摘要的黄金样本。
- [x] 确认 Flake8/Pylint 等价静态检查已通过 pre-commit 配置，现阶段只报告既有问题。

交付物：

- 测试基线说明。
- 回归数据样本。
- 公开接口清单。
- 已知问题清单。

完成标准：后续每个阶段可以明确判断是否改变了现有行为。

阶段状态：已完成（2026-09-16）。

## 阶段 1：公共 I/O 与 Artifact 基础能力

目标：先消除低风险、明确重复的实现。

步骤：

- [x] 新增 `axonx/utils/fs/atomic.py`。
- [x] 新增 `axonx/utils/fs/checksum.py`。
- [x] 为异常清理、覆盖、Unicode、非有限浮点数增加单测。
- [x] 将 Plugin 的 SHA-256 切换到公共实现。
- [x] 将 Alpha158 的 SHA-256 和原子写入切换到公共实现。
- [x] 将 TaskManager 和 Plugin 状态保存切换到公共原子 JSON 写入。
- [x] 删除重复实现。

完成标准：仓库中只有一个文件 SHA-256 和一个通用原子 JSON 实现。

阶段状态：已完成（2026-09-16）。

### 阶段 0、阶段 1 实施记录

重构开始前已记录工作区状态，并将已有修改视为用户工作，不覆盖、不回退。

重构前测试基线：

```text
pytest -q
172 passed in 11.63s
```

阶段 1 完成后的测试结果：

```text
pytest -q
180 passed in 10.71s
```

新增的公共 I/O 文件和测试已通过项目现有的 pre-commit 检查，包括 Black、Flake8、Pylint 和 Pyroma。

阶段 0 和阶段 1 已确认以下公开契约保持不变：

- `axonx` CLI 命令和参数格式。
- HTTP endpoint、方法、响应 Schema 和 MCP Tool。
- Component、Job、Task 的公开调用接口。
- Alpha158 Task 名称、Artifact 文件名、metadata 字段和 `schema_version`。
- Plugin wheel、Manifest、安装状态文件和贡献注册格式。
- TaskManager `status.json` 的字段和值语义。

已完成的保护面包括：

- CLI 参数、主要输出和远程调用行为。
- HTTP Job、插件上传、代理和 Workspace API。
- 组件依赖顺序、启动失败回滚和关闭。
- TaskManager 提交、退出、取消、恢复和状态文件异常。
- Alpha158 固定小样本、管线输出、Artifact metadata、Schema、行数和摘要。

Alpha158 和 Tushare 保持 `axonx` 原生能力，不迁移为插件。项目继续使用 pre-commit 中已有的 Flake8 和 Pylint 配置，不执行无关的全仓格式化。

## 阶段 2：Application、ComponentGraph 与生命周期

目标：分离应用构建、依赖图和调用分发，同时让 `Application` 直接拥有生命周期。

步骤：

- [x] 从 `Application` 提取 `ComponentGraph`。
- [x] 为缺失依赖、可选依赖、循环依赖和稳定顺序增加测试。
- [x] 将启动、回滚和关闭逻辑内聚到 `Application`。
- [x] 验证部分启动失败时只关闭已启动组件。
- [x] 提取 `JobDispatcher`。
- [x] 提取 `ApplicationBuilder`。
- [x] 保留原 `Application` API 作为门面。

完成标准：`Application` 负责生命周期和公开 API，但不再包含构建、拓扑排序和远程分发细节。

阶段状态：已完成（2026-09-16）。`@R.register(...)` 保留为内置 backend 的声明机制，Application 使用隔离的 Registry 副本。

## 阶段 3：LocalTaskManager

目标：隔离进程、状态机、持久化和日志能力。

步骤：

- [x] 提取 `TaskStatusRepository`。
- [x] 提取 `TaskLogLocator`。
- [x] 提取 `TaskStateReconciler`。
- [x] 提取 `TaskProcessSupervisor`。
- [x] 为状态变更加统一异步锁。
- [x] 将磁盘读写移出事件循环线程。
- [x] 验证 shutdown 时先终止 worker，再保存最终状态。
- [x] 验证延迟状态不会覆盖 CANCELLED 或 FAILED。
- [x] 保持现有 `BaseTaskManager` 接口。

完成标准：`LocalTaskManager` 成为薄门面，各子模块可以独立单测。

阶段状态：已完成（2026-09-16）。`LocalTaskManager` 已收敛为编排门面，状态变更统一加锁，持久化通过线程执行。

## 阶段 4：HTTP、MCP 与 Workspace

目标：让传输层只承担协议转换。

步骤：

- [x] 引入 FastAPI 应用工厂。
- [x] 拆分 Job Router。
- [x] 拆分 Plugin Router。
- [x] 拆分 MCP 注册器。
- [x] 拆分静态站点挂载。
- [x] 建立内部异常到 HTTP 状态码的统一映射。
- [x] 提取 Workspace 路径解析器。
- [x] 提取 Workspace 浏览、预览和删除服务。
- [x] 将现有 Workspace Step 改成薄适配器。

完成标准：HTTP 模块不直接处理插件状态文件、Workspace 文件格式或 TaskManager 内部状态。

阶段状态：已完成（2026-09-16）。`HttpService.build_service()` 已委托给应用工厂，Job、插件上传、MCP 和静态站点装配已分离；HTTP 预期错误统一映射；Workspace 路径、浏览、预览和删除已移入独立服务，Step 只负责适配。完整测试：190 passed。

## 阶段 5：插件系统

目标：拆开 wheel 构建、检查、安装、持久化和贡献索引。

步骤：

- [x] 提取 Artifact Inspector。
- [x] 提取 Plugin Builder。
- [x] 提取 Plugin Installer。
- [x] 提取 Plugin Repository。
- [x] 提取贡献冲突检测器。
- [x] 使用 `PluginService` 编排用例。
- [x] 补充安装失败、摘要错误、Manifest 冲突和重复安装测试。
- [x] 审查远程安装默认配置和 token 策略。

完成标准：插件安装流程不再集中在 `LocalPluginComponent` 中。

阶段状态：已完成（2026-09-16）。`LocalPluginComponent` 保留公开接口并委托 `PluginService`；原 `axonx.plugin.artifact` 路径继续 re-export。检查已保存的 wheel 时会核对摘要。完整测试：200 passed；新增和修改的 Python 文件通过 pre-commit 检查。

安全审查：`LocalPluginComponent` 构造默认禁用远程安装，但内置 `config/default.yaml` 显式启用，且未配置 `install_token`；HTTP 上传此时无需 token。阶段 5 保持现有默认配置语义，仅记录此风险；如需改为默认禁用或强制 token，应作为单独的外部配置契约变更处理。

## 阶段 6：Alpha158 内部重构

目标：先在原路径内降低复杂度，不立即移动包。

步骤：

- [ ] 为 ETL、训练、预测、分析、回测建立 Typed State。
- [ ] 提取公共 Artifact Reader/Writer。
- [ ] 将 ETL 数据加载与校验拆开。
- [ ] 将特征、标签、市场状态计算改为纯函数模块。
- [ ] 将训练数据准备、调参、最终训练、评估和输出拆开。
- [ ] 将预测输入解析、模型加载、推理和发布拆开。
- [ ] 将因子指标和分组收益计算拆开。
- [ ] 将回测持仓、换手、基准和统计计算拆开。
- [ ] 对固定样本比较重构前后的数值结果。
- [ ] 保持 metadata schema 和文件名不变。

完成标准：Task 类主要描述步骤和进度，不再直接包含大量数据计算和文件协议逻辑。

## 阶段 7：原生业务边界与注册治理

目标：Alpha158 和 Tushare 保持原生集成，同时与通用运行时建立单向依赖边界。

步骤：

- [ ] 明确 `tasks/alpha158`、`tasks/data` 与通用 Task 运行时的依赖规则。
- [ ] 确认 Alpha158 和 Tushare 继续通过 `@R.register(...)` 注册，并增加内置 Task 清单测试。
- [ ] 迁移 Task、Connector 和业务配置时保留旧路径 re-export。
- [ ] 增加 import 契约和内置 Task 注册测试。
- [ ] 禁止通用运行时反向 import 原生量化业务实现。
- [ ] 保持 LightGBM、Polars、Pandas、PyArrow 等量化依赖由主项目管理。
- [ ] 更新原生能力的开发和迁移文档。
- [ ] 验证默认安装可直接使用 Alpha158 和 Tushare 能力。

完成标准：Alpha158 和 Tushare 仍由 `axonx` 原生提供，通用运行时与业务实现之间保持单向依赖。

## 阶段 8：清理与稳定

步骤：

- [ ] 删除已经没有调用方的兼容内部代码。
- [ ] 更新 README 和架构文档。
- [ ] 增加模块依赖检查，禁止原生业务实现反向进入通用运行时。
- [ ] 收紧类型检查范围。
- [ ] 运行完整回归和性能对比。
- [ ] 输出升级说明。

## 8. 测试策略

## 8.1 测试层次

| 层次 | 目标 | 示例 |
| --- | --- | --- |
| 纯函数单测 | 验证计算逻辑 | 日期、路径、特征、标签、指标 |
| 组件单测 | 验证单个服务 | Repository、Graph、Reconciler |
| 契约测试 | 固定公开协议 | CLI、HTTP、MCP、metadata |
| 集成测试 | 验证模块组合 | Application 启停、Task worker、插件安装 |
| 黄金样本测试 | 防止数值漂移 | Alpha158 小样本结果 |

## 8.2 Alpha158 数值验证

不能只比较列名，应至少比较：

- 行数和交易日范围。
- 股票代码集合。
- Schema 和列顺序。
- null、NaN、Infinity 数量。
- 关键特征的分位数与均值。
- 标签值与有效性标记。
- 训练集、验证集划分。
- best iteration 和评估指标容差。
- 预测排序的一致性。
- 回测净值、换手率和统计指标容差。
- Artifact 文件和 metadata 内容。

浮点比较必须设置明确容差，不能使用不受控的字符串快照。

## 8.3 并发与失败测试

重点覆盖：

- 两个状态更新同时到达。
- worker 在第一次状态上报前退出。
- manager 关闭时 worker 忽略 SIGTERM。
- 状态文件损坏或被复制自其他 workspace。
- 组件启动到一半抛出异常。
- 多个 Job 同时执行并在关闭时被取消。
- 插件安装到一半失败。
- HTTP 请求超过限制或客户端提前断开。

## 9. 兼容策略

### Python API

- 保留 `axonx.Application`。
- 保留现有 BaseComponent、BaseJob、BaseTask 等公开导入路径。
- 迁移后的类先通过旧模块 re-export。
- 弃用期内不得直接删除旧路径。

### CLI

- 命令名称和参数解析规则保持不变。
- 标准输出与标准错误用途保持不变。
- 错误类型重构后，退出码仍遵循当前约定。

### HTTP/MCP

- Endpoint、方法和响应 Schema 保持不变。
- MCP Tool 名称、描述、输入和输出 Schema 保持不变。
- 内部 Router 拆分不能改变 OpenAPI 契约。

### 配置

- 现有 YAML 字段保持可用。
- 新配置字段提供默认值。
- 配置迁移应集中在 Resolver 或 Migration 中，不能散落在组件构造函数。

### Artifact

- 保持现有目录、文件名和 `schema_version`。
- 如果必须升级 Schema，Reader 至少支持当前版本和上一个版本。
- 每次 Schema 变化必须提供迁移说明和契约测试。

## 10. 代码质量规则

以下数字用于发现问题，不作为机械硬限制：

- 单文件超过约 300 行时检查是否存在多个职责。
- 方法超过约 50 行时检查是否可以提取纯计算或用例步骤。
- 三处以上相同业务流程应考虑抽取公共模块。
- 两处完全相同的基础设施实现应直接统一。
- 避免超过三层的深嵌套分支。
- 对外方法和跨模块模型必须有类型标注。
- 不使用布尔参数控制完全不同的行为；优先拆分方法或策略对象。
- 不允许业务模块直接 import FastAPI、Uvicorn 或 CLI 表示层。
- 不允许通用运行时模块 import Alpha158 或 Tushare 的具体实现。

抽取代码前要确认抽象名称表达真实概念。仅仅代码形状相似、业务语义不同的逻辑不应强行复用。

## 11. 提交与审查策略

建议每个提交满足：

- 只处理一个明确边界。
- 测试与代码在同一提交中。
- 文件移动与逻辑修改尽量分开。
- 不混入大规模格式化。
- 提交信息说明行为是否变化。
- 提供重构前后模块映射。

推荐提交序列示例：

```text
test: characterize atomic artifact writes
refactor: centralize atomic filesystem operations
test: characterize component dependency ordering
refactor: extract component graph
refactor: extract application lifecycle manager
test: cover task process reconciliation
refactor: split local task status repository
```

每个阶段完成后再合并，不建议维持一个持续数周、同时修改所有模块的大分支。

## 12. 风险与控制措施

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 大量移动导致 import 断裂 | 插件或外部用户无法启动 | 旧路径 re-export，增加 import 契约测试 |
| Alpha158 数值漂移 | 模型和回测结果改变 | 固定样本、统计比较、明确浮点容差 |
| 生命周期改变 | 资源泄漏、关闭死锁 | 失败注入测试、反向关闭测试 |
| 状态持久化竞态 | Task 状态丢失或被覆盖 | 单一写入口、异步锁、原子替换 |
| 装饰器注册遗漏内置实现 | Task 或 Backend 缺失 | Registry 清单测试、应用构建测试 |
| 内部模块移动破坏默认安装 | CLI 或原生任务无法启动 | 默认安装 CI、公开 import 契约测试 |
| HTTP 拆分改变路由优先级 | SPA fallback 吞掉 API | 路由表快照和端到端测试 |
| 与现有未提交修改冲突 | 用户工作丢失 | 每阶段先检查工作区，禁止覆盖无关文件 |

## 13. 完成定义

整个后端重构完成需同时满足：

- [ ] 完整测试套件通过。
- [ ] 核心公开 API、CLI、HTTP、MCP 契约有自动化测试。
- [ ] Alpha158 黄金样本结果在约定容差内一致。
- [ ] `Application`、`HttpService`、`LocalTaskManager` 均已成为职责清晰的门面。
- [ ] 文件摘要、原子写入、Artifact 基础模型不存在重复实现。
- [ ] Task 状态持久化只有一个写入口。
- [ ] Workspace 路径安全只有一个权威实现。
- [ ] 通用运行时不反向依赖 Alpha158 或 Tushare 的具体实现。
- [ ] Alpha158 和 Tushare 作为原生能力通过 Registry 注册并有完整清单测试。
- [ ] 旧导入路径有明确兼容期或已经完成迁移。
- [ ] README、架构图、插件开发文档和升级说明已经更新。
- [ ] 没有为了重构引入无实际用途的抽象层。

## 14. 推荐的首个实施批次

首个批次建议严格控制在以下范围：

1. 为现有原子写入和 SHA-256 行为补测试。
2. 新增 `axonx/utils/fs/atomic.py` 和 `axonx/utils/fs/checksum.py`。
3. 替换 Plugin 与 Alpha158 中的重复 SHA-256。
4. 替换 Plugin、TaskManager 和 Alpha158 中能够安全统一的原子 JSON 写入。
5. 运行完整测试并确认输出契约未变化。

该批次不移动大型模块、不修改业务公式，也不改变公开 API。完成后再进入 Application 与生命周期拆分。

## 15. 实施前注意事项

当前仓库存在未提交修改和新增/删除文件。开始编码前必须：

1. 使用 `git status --short` 明确已有改动。
2. 将现有改动视为用户工作，不覆盖、不回退。
3. 重构文件与已有修改重叠时，先检查差异再编辑。
4. 每个阶段只提交本阶段涉及的文件。
5. 禁止使用破坏性 Git 命令清理工作区。

本方案的核心不是把代码拆得越碎越好，而是让每个模块只承担一种能够被清楚命名、独立测试和稳定复用的职责。
