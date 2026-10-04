# Studio 入门

官网导航中的 **Playground** 可直接体验 Studio，无需启动服务。示例包括完整研究链路与两组回测。打开任务提交，选择 `playground.backtest`，设置 `strategy` 与 `outcome`，提交后在任务中心查看进度、日志及结果，也可以取消执行。成功任务会出现在回测页；策略比较可对比两组示例。Agent 为脚本回复。所有数据与执行均为模拟，刷新或点击「重置示例」恢复初始状态。

AxonX Studio 是任务与研究工作台。它读取服务提供的 Job 和 Task 定义，用 Schema 生成提交表单，并展示运行状态、日志、依赖关系与标准研究产物。

![Studio navigation](../../figures/getting-started/studio-map.svg)

本文截图使用英文界面，正文使用中文。截图展示实际页面；可见任务和插件数量取决于当前机器。真实实验的任务标识、私人路径、远程地址与浏览器标签栏不作为文档素材保留；任务操作截图中的 `docs-demo` 和 `docs-child` 是专门创建的内置演示。

## 打开 Studio

安装 AxonX 与 Studio 后启动服务（`axonx[full]` 也包含 Studio）：

```bash
pip install "axonx[studio]"
axonx start --service.host 127.0.0.1
```

启动前配置[服务 token](../guides/authentication.md)，然后打开 `http://127.0.0.1:1024/`。AxonX 从 `axonx_studio` Python 包加载静态页面。未安装 Studio 时，API 仍可工作。

前端开发与代理配置见 [Studio 开发](../development/studio.md)。

## 配置连接

进入右上角 **Settings**，在 **Service token** 输入本机服务使用的 token。浏览器会保存本机 token，清除时使用同一个设置入口。截图只显示 “Token configured” 状态，不包含凭据值。

![Studio settings in English](../../figures/studio/settings.png)

机器选择器默认是 **Local**。配置远程目标后，选择器列出服务的 `targets`。Studio 仍向同源后端请求，远程地址通过请求外层 `target` 发送，远程 token 保存在后端配置中。

切换机器会改变可用任务定义、运行记录和研究结果。操作前确认当前目标，尤其是提交、取消和删除。连接差异见[远程机器使用](../guides/remote-machines.md)。

## 从提交表单到任务详情

![Demo Task form in English](../../figures/studio/submit-demo.png)

1. 进入 **Submit task**，在 **Native tasks** 中选择 `demo`。
2. 填写 `X` 与 `Y`，例如 `2` 和 `3`；`Fail` 保持 `False`。
3. 可填写 `Task Name` 方便查询，或者留空生成名称。`Source Tasks` 接受英文逗号分隔的 Task ID。
4. 点击 **Submit run**，提交成功后进入 **Task management** 查看运行。
5. 打开任务详情，核对状态、步骤、日志、依赖图和最终输出。

表单来自 Task 的 `input_schema`。必填字段、枚举、布尔值、数字和 JSON 对象按字段类型处理；空白可选字段不会自动变成空字符串提交。后端仍执行实际模型校验，复杂 Schema 约束不能只依赖表单展示。

固定实例名的重跑会替换已结束任务目录。需要保留多次实验时，用不同 Task Name 或生成名称。详见[生命周期](../concepts/task-lifecycle.md)。

## 使用任务与资源页面

![Task operations with two documentation demos](../../figures/studio/task-list.png)

截图中的两个演示均已成功；操作详情、日志和关系图见[任务管理](../guides/task-management.md)与[任务血缘](../concepts/task-lineage.md)。

**Task management** 提供任务类型、状态与名称筛选，支持每 5 秒自动刷新、查看详情、取消和多选删除。活跃任务的详情通过事件流展示进度和日志；结束后的日志可以按需读取。

依赖图显示任务与上游关系。运行中的关系可能来自状态配置，成功任务的关系来自元数据；缺少上游记录时会显示缺失节点。图中的关系不是自动执行计划。

**Machine resources** 显示当前目标的 CPU、内存和 GPU 指标。设备数据取决于所在机器与可用的厂商工具；没有 GPU 数据不意味着一定有 GPU 故障，也不代表框架会自动选机或分配设备。

## 查看研究结果

| 页面                | 主要内容                       | 详细说明                                       |
| ------------------- | ------------------------------ | ---------------------------------------------- |
| 原始数据            | 原始数据目录与 Parquet 预览    | [数据下载](../research/tushare.md)             |
| ETL                 | 数据行数、日期范围、特征和标签 | [结果解读](../research/results.md)             |
| Factor analysis     | 因子评分与指标分组             | [结果解读](../research/results.md)             |
| Model training      | 模型配置、指标、训练曲线       | [产物协议](../reference/research-artifacts.md) |
| Offline prediction  | 预测数据、统计和产物           | [结果解读](../research/results.md)             |
| Offline backtest    | 日频曲线、质量和分期汇总       | [回测解读](../research/backtest.md)            |
| Strategy comparison | 两个回测的共同区间比较         | [策略比较](../research/strategy-comparison.md) |

**原始数据** 浏览 `workspace_dir/tushare`。年份（`YYYY`）与日期（`YYYYMMDD`）目录按时间倒序显示；其他目录和文件保留名称升序，目录优先。服务连接指示器每 15 秒检查状态。任务列表与服务状态的自动检查在浏览器标签页隐藏时暂停，回到前台后立即检查；请求尚未完成时不会重复发送。研究页面与文件页面按需刷新。复制成功提示统一显示 1.6 秒，每次复制后重新计时。

研究页面读取 `metadata.json` 及 `output_params.artifacts`。任务列表里有一条运行记录，并不保证它已产生可展示的研究元数据。失败任务、字段不完整或损坏的 metadata 应先在详情和日志中排查。

研究页面的删除操作删除所选目录和产物；下游依赖不会因此自动重建。删除前确认需要保留的实验，操作语义见[工作区文件](../guides/workspace-files.md)。

## Agent 与 API 入口

**Agent** 支持续接会话、查看文本与工具调用、停止当前轮次，以及会话重命名、标签、分叉和删除。任务详情中的解释入口可把 Task ID 带到 Agent，但实际对话需要可用的模型配置。停止对话不等于取消 Task。

**API interfaces** 从当前目标的 Job 目录生成调用表单。它调用的是 Job，而不是直接执行任意 Task：例如先选择 `get_task_definition` 查定义，再用 `submit` 提交注册任务。普通调用返回响应，流式协议详见 [SSE 事件](../api/events.md)。

![Public API version response](../../figures/studio/api-response.png)

上图实际调用只读 `version` 接口，显示 HTTP 200 与版本字符串。其他接口可能提交任务或改变数据，调用前应核对其语义。

## 页面链接与偏好

页面路由使用 `#机器/页面/视图/资源`，例如 `#local/task-defs/catalog/demo`。资源部分由路由进行编码；复制 Task ID 到命令行时应作为完整字符串加引号。

语言、主题和面板宽度保存在浏览器偏好中，不改变服务端研究配置。本文截图统一使用英文显示，中文界面可通过顶部语言按钮切换。

## 功能截图索引

| 功能                                 | 截图所在文档                                   |
| ------------------------------------ | ---------------------------------------------- |
| 主页、提交 demo、设置、API 调试      | [快速开始](quickstart.md)与本文                |
| 任务列表、详情和日志                 | [任务管理](../guides/task-management.md)       |
| 参数快照和关系图                     | [任务血缘](../concepts/task-lineage.md)        |
| CPU、内存和 GPU                      | [远程机器](../guides/remote-machines.md)       |
| Agent 新会话                         | [Agent 使用](../agent/usage.md)                |
| 数据下载表单、Parquet 预览           | [Tushare 数据](../research/tushare.md)         |
| ETL、因子、训练参数与曲线、预测      | [研究结果](../research/results.md)             |
| 收益、质量、持仓、总体及年/季/月汇总 | [回测解读](../research/backtest.md)            |
| 策略比较五个页签                     | [策略比较](../research/strategy-comparison.md) |
| 通知任务表单                         | [通知](../research/notifications.md)           |

## 首次使用的空状态

![Task operations before submitting a demo](../../figures/studio/runtime.png)

尚未运行任务时，列表显示空状态。提交本页 demo 后可获得前文展示的成功记录；无需执行完整研究流程才能验证连接。

## 出现问题时

| 表现                        | 先检查                                                   |
| --------------------------- | -------------------------------------------------------- |
| 页面能打开，但 API 返回 401 | 本机 token 与服务配置是否一致                            |
| 任务定义或 API 目录为空     | 服务是否配置 token、插件是否在选定机器安装、Job 是否公开 |
| 研究页没有结果              | 对应 metadata 是否生成并包含标准输出                     |
| 图表缺少曲线                | training_curve、daily、summary 等字段或文件是否存在      |
| 远程机器请求失败            | 后端 targets 的地址、token 与目标服务连通性              |

更多说明见[常见问题](../faq.md)、[排障与恢复](../guides/operations.md)。
