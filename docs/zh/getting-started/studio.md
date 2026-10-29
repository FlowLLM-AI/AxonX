# 使用 AxonX Studio

## 打开 Studio 并配置连接

![AxonX Studio 0.3.0 home](../../figures/studio/home.png)

[查看高清原图](../../figures/studio/home.png)

截图使用 Studio 0.3.0 完整英文界面，以浏览器 2 倍像素密度保存。Playground 提供虚构数据与模拟执行；真实服务展示其已安装 Task 和已配置机器。

安装 axonx[studio] 或从源码构建/安装 axonx_studio，然后运行 `axonx app`。打开 http://127.0.0.1:1024，在浏览器设置中填写服务 token。即使认证数据 Job 不可用，静态 UI 也可能加载。执行或修改文件前先选定目标机器。

## 研究与开发入口

当前导航分为系统管理、日常运行、研究分析和开发工具。系统管理包含全部任务、机器资源、运行环境和工作区；开发工具包含任务定义和 API接口；研究分析包含智能体、数据处理、因子分析、模型训练、离线预测、离线回测和策略对比；日常运行包含在线预测、预测比对和数据更新。

**数据处理**展示 ETL 任务生成的数据集与产物，供因子分析、训练和预测复用。**预测比对**核对同一时点的在线与离线模型输入、预测分数及候选排名；**策略对比**比较两份离线回测的收益、风险与持仓。

## 执行任务并检查详情

![Studio task definitions, input parameters and expected output](../../figures/studio/task-definitions.png)

[查看高清原图](../../figures/studio/task-definitions.png)

截图在静态 Playground 中选择 `playground_train`。连接真实服务后，选择实际要执行的已安装 Task。

打开 **开发工具 → 任务定义**，选择 demo、阅读 Schema，填写 x/y 和可选 task_name。执行通过服务 cli 命令并展示输出，命令连接和持久化 metadata 独立跟踪。创建进程不代表成功，应检查命令终态、Task 状态和业务输出。连接失败单独显示，重试前先调查执行证据。

任务详情显示 started_at、步骤、日志、子任务、输入输出和关系。停止操作检查当前启动身份后调用 CLI kill。子任务共享根执行进程，删除目录不会停止写入者。

## 工作区与资源

![Studio workspace tree and Markdown preview](../../figures/studio/workspace-preview.png)

[查看高清原图](../../figures/studio/workspace-preview.png)

工作区位于系统分组，路由为 `#local/workspace/files`。按需浏览目录、加载更多条目并预览文本/结构化/表格文件，Markdown 提供渲染和有限源码视图。路径属于所选工作区，删除前核对写入状态。机器资源展示实际 CPU/内存/GPU，不自动分配设备。

## 查看研究结果

数据处理、因子分析、模型训练、离线预测、离线回测页面读取 metadata 和已发布产物。策略对比要求日期、协议和股票范围兼容。在线预测、预测比对、数据更新页面按 `report_kind` 选择 Task 报告。副本缺失/省略文件、行情不完整需要明确解释，Task 成功不代表研究评价完整。

研究截图使用 Playground 合成 Task 与产物展示当前界面中的控件和字段，指标为虚构示例。详见[研究结果](../research/results.md)和[回测](../research/backtest.md)。

## Agent 与 API 入口

![Studio API catalog with get_task_def request and response](../../figures/studio/api-catalog.png)

[查看高清原图](../../figures/studio/api-catalog.png)

Agent 要求后端模型配置，支持存储会话、展示补丁和轮次中断，独立研究执行有自己的生命周期。API 接口读取当前 Job 目录；get_task_def 查询定义，原生命令通过 cli argv 执行。远程插件部署遵循构建/上传/安装/清理，不把本地路径直接传给远程命令。

## 页面链接与偏好

路由为 `#machine/section/view/resource`，routeHash 编码含 # 的资源 ID。Task 定义示例为 `#local/task-defs/catalog/demo`。浏览器语言/主题/面板偏好不改变服务研究配置。切换机器后请求需保持正确 target，避免旧响应覆盖。

## 空状态与失败

新工作区为空是正常情况。先运行 Demo 取得证据再配置研究。401 检查本地 token；定义缺失时检查目标插件环境并重启常驻目录；图表缺失时检查产物契约与文件覆盖。静态页面可加载不代表后端就绪。

[快速开始](quickstart.md) · [任务管理](../guides/task-management.md) · [插件部署](../plugins/management.md) · [Agent 配置](../agent/configuration.md)
