# AxonX Studio

[English](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/README.md) · 简体中文

AxonX Studio 是 [AxonX](https://github.com/FlowLLM-AI/AxonX/blob/main/README_ZH.md) 的浏览器工作台：通过 Agent 开发研究插件，在选定服务提交 Task，查看日志、产物与图表。后端负责执行任务，插件提供研究算法。

![AxonX Studio 主页](https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/docs/figures/studio/home.png)

首页截图使用静态 Playground 的英文界面，数据与执行均为模拟。

## 主要功能

| 功能           | 能力                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------- |
| 任务定义       | 配置已安装任务的参数，通过 CLI Job 运行，查看输出字段与实时日志。                                   |
| 任务管理       | 筛选任务，查看配置、进度、日志、依赖和父子调用；研究索引支持删除选中结果。                          |
| 机器管理       | 切换本机与已配置的远程目标，查看 CPU、内存、GPU 和运行环境信息。                                    |
| 工作区         | 在系统管理中浏览工作区，支持目录与 Parquet 分页，以及 Markdown 原始/预览切换和 frontmatter 元信息。 |
| 研究结果       | 查看 ETL 数据集、因子指标、训练配置与曲线、预测产物。                                               |
| 回测与策略比较 | 查看收益曲线、质量指标、持仓和年/季/月汇总，在共同日期区间比较两个回测。                            |
| Agent          | 流式展示回答与工具调用、续接会话、重命名/标签/分叉/删除会话，以及停止当前轮次。                     |
| API 调试       | 浏览当前机器的 Job 目录，通过 Schema 表单调用 API。                                                 |

界面支持英文与简体中文、明暗主题，并保存浏览器偏好。Hash 路由保留所选机器与资源，例如 `#local/task-defs/catalog/demo`。

## 安装与启动

使用已激活的 Python 环境，要求 **Python 3.12+**。本地 Task 执行支持 macOS 和 Linux。预构建 Studio 包无需 Node.js 或本地前端构建。

```bash
pip install "axonx[studio]"
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx app --service.host 127.0.0.1
```

打开 <http://127.0.0.1:1024/>，在 **设置 → 本机服务令牌**（英文界面为 **Settings → Local service token**）输入相同 token 并应用。Studio 将 token 保存在浏览器 local storage 中，通过 Bearer token 验证 API 请求。可在同一设置表单中替换或清除 token。

也可以在启动 AxonX 的目录中创建 `.env`，设置 `AXONX_SERVICE_TOKEN`。CLI 自动加载该文件，已有环境变量优先。可选的服务商配置见 [example.env](https://github.com/FlowLLM-AI/AxonX/blob/main/example.env)。

如果已经安装 AxonX，可单独添加 Studio：

```bash
pip install axonx-studio
```

安装后重启服务。AxonX 通过包中的 `static_dir()` 加载 `dist/`，在启用 `service.web_enabled` 时将界面托管到 `/`。

### 运行第一个任务

1. 打开 **任务定义**，选择 `demo`，填写 `x = 2`、`y = 3`，点击 **运行任务**。
2. 任务记录生成后进入详情，查看配置、步骤、日志与关系。
3. 右下角运行记录在站内切换页面和机器时保留，可返回原执行目标查看结果。

Studio 通过现有 `cli` Job 保持流式执行连接；站内导航不会取消执行，刷新、关闭页面或连接中断可能终止命令。字符串数组支持逐项添加与删除，对象和复杂数组使用 JSON 输入。也可使用 CLI `axonx exec --task demo --x 2 --y 3`，或让已配置的 Agent 执行。

任务名称留空时生成新名称；复用固定名称会替换已结束运行的结果。`upstream_task_ids` 记录直接输入依赖，不会自动执行上游任务；`parent_task_id` 和 `children` 记录父子调用，两者保持独立。

### 可选的研究与 Agent 配置

- **研究插件：** 在执行服务的 Python 环境安装 `axonx-qlib-a158`、`axonx-qlib-factor` 或 `axonx-qlib-strategy`，然后重启服务。研究视图需要已完成的运行及标准 `metadata.json` 和产物输出。
- **Tushare 下载：** 在后端配置 `AXONX_TUSHARE_TOKEN`。仅在使用兼容的自定义接口时覆盖 `AXONX_TUSHARE_BASE_URL`。
- **Agent：** 按服务商要求在后端配置 `CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL` 和 `CLAUDE_CODE_MODEL_NAME`。普通 Task 无需模型凭据即可运行。停止 Agent 当前轮次不会取消它已提交的 Task。
- **远程机器：** 配置后端服务的 `targets`，然后在 Studio 中选择目标。浏览器向本机服务认证，后端解析远程地址与凭据，通过 `target` 转发请求。

详见[研究环境准备](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/research/workflow.md)、[Agent 配置](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/agent/configuration.md)与[远程机器](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/guides/remote-machines.md)。

### 使用 Agent 研究

将研究问题和 [AxonX Skill](https://github.com/FlowLLM-AI/AxonX/blob/main/skills/axonx/SKILL.md) 交给外部或内置 Agent。内置开发需要配置源码访问与文件／命令工具，详见 [Agent 配置](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/agent/configuration.md)。先开发插件，再安装到选定服务，最后提交 Task，并等待上游成功。

Qlib Alpha158 参考流程为 **ETL → 训练 → 预测 → 回测**，因子分析从 ETL 独立分支。`qlib_a158`、`qlib_factor` 与 `qlib_strategy` 分别提供基线、可选因子和组合策略。比较运行时，保留代码、数据、窗口、参数、成本及 Task ID 和开始时间。详见[研究流程](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/research/workflow.md)。

## npm 分发与静态托管

npm 包提供构建后的前端资源：

```bash
npm install @flowllm-ai/axonx-studio
```

使用静态服务器托管 `node_modules/@flowllm-ai/axonx-studio/dist/`，同时提供 AxonX 后端。前端使用相对于当前源的 API URL，因此需将同源的 `/health`、`/jobs`、`/upload`、`/mcp` 和 `/proxy` 代理到后端。代理应保留 Authorization 请求头并支持 SSE 流式传输，以展示实时日志和 Agent 回答。页面使用 Hash 路由，无需为各个 Studio 页面配置服务端路由。

使用 AxonX 内置托管时，安装 Python 包即可。

## 源码开发

根据 `package.json`，前端工具链要求 **Node.js 22.x ≥ 22.13.0、24.x 或 26+**。从仓库根目录安装后端及开发依赖：

```bash
pip install -e '.[dev]'
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx app --service.host 127.0.0.1
```

在另一个终端运行：

```bash
cd axonx_studio
npm ci
npm run dev
```

打开 <http://localhost:4173/>，为该浏览器源配置服务 token。Vite 提供热更新，默认将 API 请求代理到 `http://127.0.0.1:1024`。

连接其他后端：

```bash
AXONX_DEV_SERVER=http://127.0.0.1:2048 npm run dev
```

Vite 也会读取仓库根目录的 `.env` 文件。修改 `AXONX_DEV_SERVER` 后重启 Vite。此设置控制开发代理，不会在生产构建中配置后端 URL。

### 构建并安装本地资源

```bash
# 在 axonx_studio/ 目录执行
npm run build
cd ..
pip install ./axonx_studio
```

`build` 先执行 TypeScript 检查，再将静态站点写入 `dist/`。重启 AxonX 后即可使用已安装包中的资源。前端修改后需重新构建并安装，才能更新包内资源。

| 命令（在 `axonx_studio/` 中执行） | 用途                                             |
| --------------------------------- | ------------------------------------------------ |
| `npm run dev`                     | 在 4173 端口启动带 API 代理的 Vite 开发服务器。  |
| `npm run build`                   | 检查类型并生成 `dist/`。                         |
| `npm run preview`                 | 本地预览生产构建；后端代理仅配置在开发服务器中。 |
| `npm run test`                    | 运行 Vitest 测试。                               |
| `npm run lint`                    | 运行 ESLint。                                    |
| `npm run format:check`            | 使用 Prettier 检查格式。                         |
| `npm run format`                  | 应用 Prettier 格式化。                           |

`npm pack` 和 `npm publish` 会自动执行 `prepack` 构建。Python 打包包含已有的 `dist/` 资源，创建 Python 分发包前需先完成构建。

## 代码结构

应用按 `app → features → shared` 分工。七个业务域分别为任务、运行环境、Agent、工作区、研究、运营和接口目录。任务定义与依赖图归入任务域；机器与服务维护归入运行环境；在线和校验报告归入运营域。共享层负责传输、文件解码、产物、异步资源、刷新、图表和基础 UI。

React 使用函数组件和 Hook；纯计算使用函数；持有资源或状态的能力由 `AxonXClient`、`ArtifactTableCache`、`SignalHistoryStore`、`RefreshScheduler` 管理。旧模块路径、仅转发的包装和重复状态别名直接删除。协议类型直接引用生成的 `shared/api/contracts.ts`，不手工修改生成内容。

请求将业务参数与 `{ target, signal }` 分开；分页与日志范围使用具名参数。同一 Task ID 的不同启动时间、不同副本快照属于不同执行身份。任务生命周期、步骤状态、数据依赖和父子调用分别表达真实后端语义。图表实例在挂载期间复用，刷新失败只在同一资源身份内保留已有数据。

后端默认提供 36 个 Job，运行时能力以 `GET /jobs` 为准。普通调用使用 `POST /jobs/{name}`，流式调用使用 `POST /jobs/{name}/events`，统一请求为 `{ arguments, target }`，统一返回为 `{ success, answer, metadata }`；SSE 必须以 `result` 事件结束。文件暂存和清理使用 `/upload`。

逐文件职责见下方[文件职责](#文件职责)。

## 常见问题

| 现象                                      | 检查项                                                                                                                             |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 后端已启动，但 Studio 不可用              | 安装 `axonx-studio`；源码构建需确认 `dist/index.html` 存在；启用 `service.web_enabled` 并重启服务。                                |
| 页面能打开，但 API 返回 401               | 确认浏览器 token 与 `AXONX_SERVICE_TOKEN` 一致；不同浏览器源分别保存 token。                                                       |
| 任务定义或 API 目录为空                   | 配置后端服务 token，确认选中的机器及其插件；未配置 token 时，服务不会公开需要认证的 Job。                                          |
| 开发时 API 请求失败                       | 确认后端正在运行、`AXONX_DEV_SERVER` 正确，修改后重启 Vite。                                                                       |
| 研究结果或曲线缺失                        | 检查任务状态、日志和 `metadata.json`，按任务类型核对 `output_params.artifacts`、`training_curve` 及回测的 `daily`/`summary` 文件。 |
| 远程请求失败                              | 检查后端 `targets`、远程服务凭据，以及本机后端到远程服务的连通性。                                                                 |
| 静态部署能打开页面，但 API 或流式输出失败 | 检查同源 API 代理路径、Authorization 转发和 SSE 缓冲配置。                                                                         |

工作区预览使用相对于执行工作区的路径。`/upload` API 用于暂存上传与清理，完整产物需从执行机器的工作区取得。删除运行或工作区条目会删除对应数据，下游结果不会自动重建。

## 文档与许可证

- [Studio 入门](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/getting-started/studio.md)
- [任务管理](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/guides/task-management.md)
- [研究产物协议](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/reference/research-artifacts.md)
- [SSE 事件协议](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/api/events.md)
- [贡献指南](https://github.com/FlowLLM-AI/AxonX/blob/main/CONTRIBUTING_ZH.md)

采用 [Apache License 2.0](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/LICENSE)。

## 文件职责

以下逐一列出源码、测试、样式、配置和源资产。`node_modules/`、`dist/`、`dist-playground/`、缓存和 Python 打包目录属于依赖或生成产物，不是另一套实现。

### 入口与应用

| 文件                                                   | 能力                                                 |
| ------------------------------------------------------ | ---------------------------------------------------- |
| [src/App.tsx](src/App.tsx)                             | 装配应用状态、外壳和页面出口。                       |
| [src/app/AppShell.tsx](src/app/AppShell.tsx)           | 顶部路径、导航、机器切换、主题语言设置和移动端外壳。 |
| [src/app/PageOutlet.tsx](src/app/PageOutlet.tsx)       | 按路由懒加载业务页面，连接页面导航与资源选择。       |
| [src/app/environment.ts](src/app/environment.ts)       | 提供构建模式和静态资源地址。                         |
| [src/app/navigation.ts](src/app/navigation.ts)         | 定义导航分组、菜单标签及路由对应的当前菜单。         |
| [src/app/routes.ts](src/app/routes.ts)                 | 定义页面路由并解析、生成机器范围内的 Hash 地址。     |
| [src/app/types.ts](src/app/types.ts)                   | 定义应用主题偏好和路径资源选项。                     |
| [src/app/useStudio.ts](src/app/useStudio.ts)           | 协调路由、主题、机器、认证、连接状态及侧栏偏好。     |
| [src/features/HomePage.tsx](src/features/HomePage.tsx) | 展示研究流程和各业务入口。                           |
| [src/i18n.ts](src/i18n.ts)                             | 加载中英文词典，选择并持久化语言，提供区域设置。     |
| [src/main.tsx](src/main.tsx)                           | 初始化语言、样式和 React；在演示构建中注入模拟传输。 |
| [src/webmcp.ts](src/webmcp.ts)                         | 在支持的浏览器中注册只读任务列表工具。               |

### 任务

| 文件                                                                                     | 能力                                                                        |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| [src/features/tasks/ExecutionSteps.tsx](src/features/tasks/ExecutionSteps.tsx)           | 呈现步骤生命周期，并折叠连续重复的已完成步骤。                              |
| [src/features/tasks/TaskChildren.tsx](src/features/tasks/TaskChildren.tsx)               | 展示每个直接子任务的最新调用及详情入口。                                    |
| [src/features/tasks/TaskDefinitionsPage.tsx](src/features/tasks/TaskDefinitionsPage.tsx) | 组织已安装定义，提供参数表单、运行入口和只读输出字段说明。                  |
| [src/features/tasks/TaskDetailPage.tsx](src/features/tasks/TaskDetailPage.tsx)           | 装配任务详情和执行日志，执行结束后重新读取状态，隔离同名任务的不同运行。    |
| [src/features/tasks/TaskGraph.tsx](src/features/tasks/TaskGraph.tsx)                     | 加载和布局依赖图，支持节点定位、导航和右键操作。                            |
| [src/features/tasks/TaskGroup.tsx](src/features/tasks/TaskGroup.tsx)                     | 呈现任务分组、展开状态、表头和组内分页。                                    |
| [src/features/tasks/TaskIssues.tsx](src/features/tasks/TaskIssues.tsx)                   | 聚合被替换任务和快照、请求异常，避免重复提示。                              |
| [src/features/tasks/TaskLogPanel.tsx](src/features/tasks/TaskLogPanel.tsx)               | 按字节读取日志，支持追踪、向前加载、复制和有界缓冲。                        |
| [src/features/tasks/TaskRow.tsx](src/features/tasks/TaskRow.tsx)                         | 展示任务身份、状态、进度和耗时；提供通用任务状态徽标。                      |
| [src/features/tasks/TasksPage.tsx](src/features/tasks/TasksPage.tsx)                     | 展示、筛选和定时刷新分组任务列表。                                          |
| [src/features/tasks/api.ts](src/features/tasks/api.ts)                                   | 封装任务定义、状态、日志、依赖图及 CLI 流式执行 Job。                       |
| [src/features/tasks/model.ts](src/features/tasks/model.ts)                               | 定义任务展示类型、状态筛选、分组排序、步骤进度、耗时及报告判断。            |
| [src/features/tasks/tree.ts](src/features/tasks/tree.ts)                                 | 递归读取记录中的子任务，验证启动时间和副本快照身份。                        |
| [src/features/tasks/execution.ts](src/features/tasks/execution.ts)                       | 持有跨页面执行连接，编码 CLI 参数，跟踪状态、日志、停止操作及精确运行身份。 |
| [src/features/tasks/TaskExecution.tsx](src/features/tasks/TaskExecution.tsx)             | 提供任务运行表单、只读输出字段、实时日志与全局运行记录。                    |

### 运行环境

| 文件                                                                                                   | 能力                                                                 |
| ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| [src/features/runtime/EnvironmentSettingsModal.tsx](src/features/runtime/EnvironmentSettingsModal.tsx) | 展示当前环境并编辑浏览器保存的本地服务令牌。                         |
| [src/features/runtime/MachineDashboard.tsx](src/features/runtime/MachineDashboard.tsx)                 | 呈现 CPU、内存和 GPU 资源图表。                                      |
| [src/features/runtime/RuntimeWorkspace.tsx](src/features/runtime/RuntimeWorkspace.tsx)                 | 装配任务、机器资源和运行环境视图。                                   |
| [src/features/runtime/UpdatePanel.tsx](src/features/runtime/UpdatePanel.tsx)                           | 发现维护能力，提交更新或重启并展示持久化进度。                       |
| [src/features/runtime/machine.ts](src/features/runtime/machine.ts)                                     | 查询机器与目标；按客户端、认证版本、目标合并并发状态请求并独立取消。 |
| [src/features/runtime/update.ts](src/features/runtime/update.ts)                                       | 发现维护 Job，提交维护操作并读取更新记录和日志。                     |
| [src/features/runtime/useMachineInfo.ts](src/features/runtime/useMachineInfo.ts)                       | 将可取消的机器资源查询接入页面和连接状态。                           |

### Agent

| 文件                                                                           | 能力                                               |
| ------------------------------------------------------------------------------ | -------------------------------------------------- |
| [src/features/agent/AgentBlock.tsx](src/features/agent/AgentBlock.tsx)         | 呈现思考、Markdown、工具输入输出和错误消息块。     |
| [src/features/agent/AgentWorkspace.tsx](src/features/agent/AgentWorkspace.tsx) | 管理会话选择、历史恢复、流式发送、停止和会话修改。 |
| [src/features/agent/AxonXMark.tsx](src/features/agent/AxonXMark.tsx)           | 呈现 Agent 使用的品牌图标。                        |
| [src/features/agent/Composer.tsx](src/features/agent/Composer.tsx)             | 处理消息输入、发送和停止按钮及键盘操作。           |
| [src/features/agent/Conversation.tsx](src/features/agent/Conversation.tsx)     | 按消息聚合会话块，呈现对话和进行中状态。           |
| [src/features/agent/SessionRail.tsx](src/features/agent/SessionRail.tsx)       | 展示会话列表及重命名、标签、分叉、删除菜单。       |
| [src/features/agent/api.ts](src/features/agent/api.ts)                         | 封装 Agent 会话 Job 与对话事件流。                 |
| [src/features/agent/reducer.ts](src/features/agent/reducer.ts)                 | 将历史记录、乐观用户消息和流式补丁合成为会话状态。 |

### 工作区与接口目录

| 文件                                                                                               | 能力                                                                                |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [src/features/api-catalog/ApiWorkspace.tsx](src/features/api-catalog/ApiWorkspace.tsx)             | 加载真实 Job 目录，编辑 Schema 参数并调用选中接口。                                 |
| [src/features/workspace/FilePreview.tsx](src/features/workspace/FilePreview.tsx)                   | 呈现数据与文档预览；Markdown 支持原始/预览、frontmatter、工作区文件链接和页内定位。 |
| [src/features/workspace/WorkspaceBrowserPage.tsx](src/features/workspace/WorkspaceBrowserPage.tsx) | 管理按需加载的目录树、目录分页、路径定位和文件预览请求。                            |

### 研究与回测

| 文件                                                                                                           | 能力                                                      |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| [src/features/research/FactorScores.tsx](src/features/research/FactorScores.tsx)                               | 按指标和标签筛选因子得分，呈现排序和幅度。                |
| [src/features/research/PredictionOverview.tsx](src/features/research/PredictionOverview.tsx)                   | 展示预测统计、样本覆盖、指数权重和输出字段。              |
| [src/features/research/ResearchDetail.tsx](src/features/research/ResearchDetail.tsx)                           | 加载研究任务，呈现身份、上游依赖和对应研究报告。          |
| [src/features/research/ResearchOutput.tsx](src/features/research/ResearchOutput.tsx)                           | 展示 ETL、训练和预测输出概览、模型成员及统一产物清单。    |
| [src/features/research/ResearchPage.tsx](src/features/research/ResearchPage.tsx)                               | 管理研究任务索引、选择、搜索、批量选择与删除。            |
| [src/features/research/TrainingCurveChart.tsx](src/features/research/TrainingCurveChart.tsx)                   | 生成训练与验证曲线、双轴范围和缩放选项。                  |
| [src/features/research/api.ts](src/features/research/api.ts)                                                   | 查询成功研究任务，验证类别与身份，并读取模型成员清单。    |
| [src/features/research/backtest/BacktestChart.tsx](src/features/research/backtest/BacktestChart.tsx)           | 把时间序列转换为 ECharts 图表选项，处理悬停、点击和缩放。 |
| [src/features/research/backtest/BacktestOverview.tsx](src/features/research/backtest/BacktestOverview.tsx)     | 协调收益和质量图表、日期范围、悬停锁定与持仓联动。        |
| [src/features/research/backtest/BacktestSummary.tsx](src/features/research/backtest/BacktestSummary.tsx)       | 呈现总体、年度、季度、月度指标及排序与对比图。            |
| [src/features/research/backtest/BacktestView.tsx](src/features/research/backtest/BacktestView.tsx)             | 选择回测股票池、加载并缓存数据，装配概览和周期汇总。      |
| [src/features/research/backtest/DateRangeSlider.tsx](src/features/research/backtest/DateRangeSlider.tsx)       | 提供可拖动且支持键盘操作的双端日期索引滑块。              |
| [src/features/research/backtest/HoldingsTable.tsx](src/features/research/backtest/HoldingsTable.tsx)           | 呈现选中交易日的持仓、排序和数值条。                      |
| [src/features/research/backtest/api.ts](src/features/research/backtest/api.ts)                                 | 解析股票池产物角色，加载完整回测或仅每日结果。            |
| [src/features/research/backtest/model.ts](src/features/research/backtest/model.ts)                             | 计算累计收益和滚动质量，定义汇总指标、排序及数值范围。    |
| [src/features/research/backtest/types.ts](src/features/research/backtest/types.ts)                             | 定义回测日表、汇总表、持仓和图表输入。                    |
| [src/features/research/compare/ComparisonPicker.tsx](src/features/research/compare/ComparisonPicker.tsx)       | 搜索回测记录，选择或取消 A、B 两个比较对象。              |
| [src/features/research/compare/ComparisonReport.tsx](src/features/research/compare/ComparisonReport.tsx)       | 呈现共同窗口中的收益、周期、质量和交易持仓对比。          |
| [src/features/research/compare/StrategyComparePage.tsx](src/features/research/compare/StrategyComparePage.tsx) | 协调两组回测、股票池、共同日期范围和比较前提提示。        |
| [src/features/research/compare/model.ts](src/features/research/compare/model.ts)                               | 对齐交易日，计算策略统计、周期收益、配对质量和持仓重叠。  |
| [src/features/research/types.ts](src/features/research/types.ts)                                               | 定义研究任务类别及按类别收窄的原始任务输出类型。          |

### 运营报告

| 文件                                                                                             | 能力                                                                              |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| [src/features/operations/CommitReport.tsx](src/features/operations/CommitReport.tsx)             | 按提交加载信号、组合或绩效表，并展示提交来源信息。                                |
| [src/features/operations/ComparePipeline.tsx](src/features/operations/ComparePipeline.tsx)       | 呈现模型校验流水线的阶段、失败原因、结果和对应日志。                              |
| [src/features/operations/ComparisonResults.tsx](src/features/operations/ComparisonResults.tsx)   | 汇总校验产物、阶段字段差异和产物链接。                                            |
| [src/features/operations/DataUpdateProgress.tsx](src/features/operations/DataUpdateProgress.tsx) | 将数据更新步骤转成状态、数量、覆盖率和异常表格。                                  |
| [src/features/operations/HistoryPreparation.tsx](src/features/operations/HistoryPreparation.tsx) | 把模型历史准备步骤与其精确子任务合成展示卡片。                                    |
| [src/features/operations/OnlineWorkbench.tsx](src/features/operations/OnlineWorkbench.tsx)       | 协调在线日期、时点、模型、采集、结果和质量页面。                                  |
| [src/features/operations/OperationIndex.tsx](src/features/operations/OperationIndex.tsx)         | 展示运营历史中的任务名称、时间和状态。                                            |
| [src/features/operations/OperationPage.tsx](src/features/operations/OperationPage.tsx)           | 按报告类型加载运营历史，选择记录并装配统一报告。                                  |
| [src/features/operations/Outcome.tsx](src/features/operations/Outcome.tsx)                       | 呈现独立窗口或预测校验结果、指标和质量。                                          |
| [src/features/operations/Performance.tsx](src/features/operations/Performance.tsx)               | 按选定日期范围呈现在线收益、回撤、换手、日表和汇总。                              |
| [src/features/operations/PipelineLogs.tsx](src/features/operations/PipelineLogs.tsx)             | 按当前模型或公共数据范围选择精确任务链日志。                                      |
| [src/features/operations/PipelineReport.tsx](src/features/operations/PipelineReport.tsx)         | 加载当前流水线及精确子任务，为在线、校验和独立报告提供数据。                      |
| [src/features/operations/PipelineSteps.tsx](src/features/operations/PipelineSteps.tsx)           | 呈现业务步骤、调度窗口、文件和采集质量。                                          |
| [src/features/operations/QualityReport.tsx](src/features/operations/QualityReport.tsx)           | 展示质量检查、样本、详情和按需导出；解析任务窗口质量。                            |
| [src/features/operations/ReportPage.tsx](src/features/operations/ReportPage.tsx)                 | 根据直接访问的任务 ID 打开对应业务报告。                                          |
| [src/features/operations/ReportTable.tsx](src/features/operations/ReportTable.tsx)               | 提供报告表格的搜索、排序、分页和展开行；业务列显式配置。                          |
| [src/features/operations/ScopeQuality.tsx](src/features/operations/ScopeQuality.tsx)             | 将质量来源限定在当前公共数据、时点或模型提交。                                    |
| [src/features/operations/SignalTable.tsx](src/features/operations/SignalTable.tsx)               | 计算信号展示统计、排名变化、股票池和可买筛选。                                    |
| [src/features/operations/StockReport.tsx](src/features/operations/StockReport.tsx)               | 协调股票报告的有效提交、历史修订、日期和展示视图。                                |
| [src/features/operations/TaskReport.tsx](src/features/operations/TaskReport.tsx)                 | 统一分派业务报告，并呈现数据更新结果、接口及任务链日志。                          |
| [src/features/operations/TopComparison.tsx](src/features/operations/TopComparison.tsx)           | 校验产物所属启动批次，展示 Top N、可买范围和逐种子差异。                          |
| [src/features/operations/api.ts](src/features/operations/api.ts)                                 | 读取在线历史清单和质量 JSON 产物。                                                |
| [src/features/operations/artifactCache.ts](src/features/operations/artifactCache.ts)             | ArtifactTableCache 合并在途表读取，按修订缓存，限制内存并管理取消。               |
| [src/features/operations/compare.ts](src/features/operations/compare.ts)                         | 解析校验模型、最新调用、所属后代、阶段状态与失败原因。                            |
| [src/features/operations/curves.ts](src/features/operations/curves.ts)                           | 按在线估值口径复利收益并计算回撤，保留未知估值。                                  |
| [src/features/operations/daily.ts](src/features/operations/daily.ts)                             | 解析模型及历史准备关系，推导时点状态；SignalHistoryStore 保留每个模型的有效历史。 |
| [src/features/operations/pages.ts](src/features/operations/pages.ts)                             | 定义运营页面的名称、图标与报告类型范围。                                          |
| [src/features/operations/report.ts](src/features/operations/report.ts)                           | 定义并验证提交、历史、报告、窗口和质量协议；计算有效修订。                        |
| [src/features/operations/signalUniverse.ts](src/features/operations/signalUniverse.ts)           | 验证股票池规则，按指数或可买股票分位数筛选信号。                                  |
| [src/features/operations/topComparisonData.ts](src/features/operations/topComparisonData.ts)     | 验证 Top N 快照并按证券代码对齐成员、排名、分数与种子。                           |

### 共享能力

| 文件                                                                         | 能力                                                              |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| [src/shared/ReplicaNotice.tsx](src/shared/ReplicaNotice.tsx)                 | 呈现副本来源、采样覆盖、遗漏文件和快照新鲜度。                    |
| [src/shared/api/artifacts.ts](src/shared/api/artifacts.ts)                   | 验证产物路径和修订，过滤副本可用产物，读取 JSON 或表格产物。      |
| [src/shared/api/client.ts](src/shared/api/client.ts)                         | AxonXClient 统一传输、令牌、目标 Job 调用、事件流和目录查询。     |
| [src/shared/api/contracts.ts](src/shared/api/contracts.ts)                   | 由后端模型生成的唯一传输类型来源；手工重构不修改此文件。          |
| [src/shared/api/event.ts](src/shared/api/event.ts)                           | 解码 SSE 帧，分派类型化事件并要求终止结果。                       |
| [src/shared/api/response.ts](src/shared/api/response.ts)                     | 校验 HTTP 与 Job 响应，提取 answer 并提供 AxonXError。            |
| [src/shared/api/tables.ts](src/shared/api/tables.ts)                         | 分页解码 Parquet 行，并统一拒绝无效或截断的 JSON 文件。           |
| [src/shared/api/types.ts](src/shared/api/types.ts)                           | 为生成的 Job 响应和目录类型补充泛型及 Schema 类型。               |
| [src/shared/api/workspace.ts](src/shared/api/workspace.ts)                   | 封装目录、预览、删除、根路径查询与有界原始文本读取。              |
| [src/shared/hooks/useAsyncResource.ts](src/shared/hooks/useAsyncResource.ts) | 管理异步资源的加载、错误、重试、取消和过期响应隔离。              |
| [src/shared/hooks/useChart.ts](src/shared/hooks/useChart.ts)                 | 统一注册图表能力，复用 ECharts 实例，清理主题和尺寸观察器。       |
| [src/shared/hooks/useCopyFeedback.ts](src/shared/hooks/useCopyFeedback.ts)   | 提供复制反馈，并清理组件退出后的反馈计时。                        |
| [src/shared/hooks/useRefresh.ts](src/shared/hooks/useRefresh.ts)             | RefreshScheduler 统一管理可见页面的刷新时钟、订阅取消和手动刷新。 |
| [src/shared/lib/errors.ts](src/shared/lib/errors.ts)                         | 提取错误文本并识别请求取消。                                      |
| [src/shared/lib/format.ts](src/shared/lib/format.ts)                         | 统一日期、字节、数字、百分比、表格值及日期输入格式。              |
| [src/shared/lib/polling.ts](src/shared/lib/polling.ts)                       | 提供可取消、页面可见时运行且不重叠的轮询计时器。                  |
| [src/shared/lib/tasks.ts](src/shared/lib/tasks.ts)                           | 从 Task ID 构造工作区目录，并读取上游任务数组。                   |
| [src/shared/lib/values.ts](src/shared/lib/values.ts)                         | 收窄 JSON 对象，并把字符串选项及标签转换为选择器数据。            |
| [src/shared/schema/values.ts](src/shared/schema/values.ts)                   | 定义 JSON Schema 与表单值，处理类型、默认值、转换和字段错误。     |
| [src/shared/ui/DataBar.tsx](src/shared/ui/DataBar.tsx)                       | 呈现正负数值条和带格式的数值单元格。                              |
| [src/shared/ui/RailResizer.tsx](src/shared/ui/RailResizer.tsx)               | 提供鼠标和键盘侧栏宽度调整。                                      |
| [src/shared/ui/ReportTabs.tsx](src/shared/ui/ReportTabs.tsx)                 | 提供受控或本地标签页、键盘导航、按需挂载和状态保留。              |
| [src/shared/ui/SchemaForm.tsx](src/shared/ui/SchemaForm.tsx)                 | 呈现参数表单、字符串列表增删控件与只读输出字段说明。              |
| [src/shared/ui/Select.tsx](src/shared/ui/Select.tsx)                         | 提供键盘可访问的选择器和原生表单适配。                            |
| [src/shared/ui/TaskIndexControls.tsx](src/shared/ui/TaskIndexControls.tsx)   | 提供任务索引标题、计数、刷新和搜索控件。                          |

### 演示环境

| 文件                                                         | 能力                                                                |
| ------------------------------------------------------------ | ------------------------------------------------------------------- |
| [src/playground/agent.ts](src/playground/agent.ts)           | 模拟会话管理、流式对话、工具结果和停止。                            |
| [src/playground/catalog.ts](src/playground/catalog.ts)       | 定义演示可用的 Job 及其输入输出 Schema。                            |
| [src/playground/comparison.ts](src/playground/comparison.ts) | 生成离线校验流水线、子任务和差异样例。                              |
| [src/playground/data.ts](src/playground/data.ts)             | 生成基础任务记录、表格、JSON、研究和回测样例。                      |
| [src/playground/fixtures.ts](src/playground/fixtures.ts)     | 装配基础研究、在线、校验、数据更新及示例文件数据集。                |
| [src/playground/online.ts](src/playground/online.ts)         | 生成在线运行、提交、历史、股票和质量样例。                          |
| [src/playground/runtime.ts](src/playground/runtime.ts)       | 实现浏览器内的 Job 查询、文件预览、删除、依赖图和静态任务事件协议。 |
| [src/playground/stream.ts](src/playground/stream.ts)         | 编码模拟 SSE，管理定时发帧、终止和请求取消。                        |

### 测试文件

| 文件                                                                                                                     | 验证能力                                                                               |
| ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| [src/app/routes.test.ts](src/app/routes.test.ts)                                                                         | 验证定义页面路由并解析、生成机器范围内的 Hash 地址及相关异常边界。                     |
| [src/app/useStudio.test.tsx](src/app/useStudio.test.tsx)                                                                 | 验证对应模块的行为及相关异常边界。                                                     |
| [src/features/agent/AgentBlock.test.tsx](src/features/agent/AgentBlock.test.tsx)                                         | 验证呈现思考、Markdown、工具输入输出和错误消息块及相关异常边界。                       |
| [src/features/agent/AgentWorkspace.test.tsx](src/features/agent/AgentWorkspace.test.tsx)                                 | 验证管理会话选择、历史恢复、流式发送、停止和会话修改及相关异常边界。                   |
| [src/features/agent/reducer.test.ts](src/features/agent/reducer.test.ts)                                                 | 验证将历史记录、乐观用户消息和流式补丁合成为会话状态及相关异常边界。                   |
| [src/features/operations/ComparePipeline.test.tsx](src/features/operations/ComparePipeline.test.tsx)                     | 验证呈现模型校验流水线的阶段、失败原因、结果和对应日志及相关异常边界。                 |
| [src/features/operations/OnlineWorkbench.test.tsx](src/features/operations/OnlineWorkbench.test.tsx)                     | 验证协调在线日期、时点、模型、采集、结果和质量页面及相关异常边界。                     |
| [src/features/operations/OperationPage.test.tsx](src/features/operations/OperationPage.test.tsx)                         | 验证按报告类型加载运营历史，选择记录并装配统一报告及相关异常边界。                     |
| [src/features/operations/PipelineReport.test.tsx](src/features/operations/PipelineReport.test.tsx)                       | 验证加载当前流水线及精确子任务，为在线、校验和独立报告提供数据及相关异常边界。         |
| [src/features/operations/QualityReport.test.tsx](src/features/operations/QualityReport.test.tsx)                         | 验证展示质量检查、样本、详情和按需导出；解析任务窗口质量及相关异常边界。               |
| [src/features/operations/SignalTable.test.tsx](src/features/operations/SignalTable.test.tsx)                             | 验证计算信号展示统计、排名变化、股票池和可买筛选及相关异常边界。                       |
| [src/features/operations/StockReport.test.tsx](src/features/operations/StockReport.test.tsx)                             | 验证协调股票报告的有效提交、历史修订、日期和展示视图及相关异常边界。                   |
| [src/features/operations/TopComparison.test.tsx](src/features/operations/TopComparison.test.tsx)                         | 验证校验产物所属启动批次，展示 Top N、可买范围和逐种子差异及相关异常边界。             |
| [src/features/operations/api.test.ts](src/features/operations/api.test.ts)                                               | 验证读取在线历史清单和质量 JSON 产物及相关异常边界。                                   |
| [src/features/operations/artifactCache.test.ts](src/features/operations/artifactCache.test.ts)                           | 验证ArtifactTableCache 合并在途表读取，按修订缓存，限制内存并管理取消及相关异常边界。  |
| [src/features/operations/curves.test.ts](src/features/operations/curves.test.ts)                                         | 验证按在线估值口径复利收益并计算回撤，保留未知估值及相关异常边界。                     |
| [src/features/operations/signalUniverse.test.ts](src/features/operations/signalUniverse.test.ts)                         | 验证验证股票池规则，按指数或可买股票分位数筛选信号及相关异常边界。                     |
| [src/features/research/PredictionOverview.test.tsx](src/features/research/PredictionOverview.test.tsx)                   | 验证展示预测统计、样本覆盖、指数权重和输出字段及相关异常边界。                         |
| [src/features/research/ResearchPage.test.tsx](src/features/research/ResearchPage.test.tsx)                               | 验证管理研究任务索引、选择、搜索、批量选择与删除及相关异常边界。                       |
| [src/features/research/api.test.ts](src/features/research/api.test.ts)                                                   | 验证查询成功研究任务，验证类别与身份，并读取模型成员清单及相关异常边界。               |
| [src/features/research/backtest/BacktestView.test.tsx](src/features/research/backtest/BacktestView.test.tsx)             | 验证选择回测股票池、加载并缓存数据，装配概览和周期汇总及相关异常边界。                 |
| [src/features/research/backtest/api.test.ts](src/features/research/backtest/api.test.ts)                                 | 验证解析股票池产物角色，加载完整回测或仅每日结果及相关异常边界。                       |
| [src/features/research/backtest/model.test.ts](src/features/research/backtest/model.test.ts)                             | 验证净值归零后不会复活，并保留毛收益加法口径。                                         |
| [src/features/research/compare/StrategyComparePage.test.tsx](src/features/research/compare/StrategyComparePage.test.tsx) | 验证协调两组回测、股票池、共同日期范围和比较前提提示及相关异常边界。                   |
| [src/features/research/compare/model.test.ts](src/features/research/compare/model.test.ts)                               | 验证对齐交易日，计算策略统计、周期收益、配对质量和持仓重叠及相关异常边界。             |
| [src/features/runtime/UpdatePanel.test.tsx](src/features/runtime/UpdatePanel.test.tsx)                                   | 验证发现维护能力，提交更新或重启并展示持久化进度及相关异常边界。                       |
| [src/features/runtime/machine.test.ts](src/features/runtime/machine.test.ts)                                             | 验证查询机器与目标；按客户端、认证版本、目标合并并发状态请求并独立取消及相关异常边界。 |
| [src/features/tasks/ExecutionSteps.test.tsx](src/features/tasks/ExecutionSteps.test.tsx)                                 | 验证呈现步骤生命周期，并折叠连续重复的已完成步骤及相关异常边界。                       |
| [src/features/tasks/TaskDefinitionsPage.test.tsx](src/features/tasks/TaskDefinitionsPage.test.tsx)                       | 验证按内置任务和插件组织已安装定义，展示输入输出 Schema及相关异常边界。                |
| [src/features/tasks/TaskDetailPage.test.tsx](src/features/tasks/TaskDetailPage.test.tsx)                                 | 验证装配配置、步骤、父子调用、日志、依赖图和报告入口及相关异常边界。                   |
| [src/features/tasks/TaskIssues.test.tsx](src/features/tasks/TaskIssues.test.tsx)                                         | 验证聚合被替换任务和快照、请求异常，避免重复提示及相关异常边界。                       |
| [src/features/tasks/TaskLogPanel.test.tsx](src/features/tasks/TaskLogPanel.test.tsx)                                     | 验证按字节读取日志，支持追踪、向前加载、复制和有界缓冲及相关异常边界。                 |
| [src/features/tasks/TasksPage.test.tsx](src/features/tasks/TasksPage.test.tsx)                                           | 验证展示、筛选和定时刷新分组任务列表及相关异常边界。                                   |
| [src/features/tasks/api.test.ts](src/features/tasks/api.test.ts)                                                         | 验证封装任务定义、摘要、完整状态、日志与依赖图 Job及相关异常边界。                     |
| [src/features/tasks/format.test.ts](src/features/tasks/format.test.ts)                                                   | 验证摘要与完整任务的步骤进度转换。                                                     |
| [src/features/tasks/groups.test.ts](src/features/tasks/groups.test.ts)                                                   | 验证按任务注册分组、状态筛选、排序和计数。                                             |
| [src/features/tasks/tree.test.ts](src/features/tasks/tree.test.ts)                                                       | 验证递归读取记录中的子任务，验证启动时间和副本快照身份及相关异常边界。                 |
| [src/features/workspace/FilePreview.test.tsx](src/features/workspace/FilePreview.test.tsx)                               | 验证呈现 Parquet、CSV、JSONL、结构化数据、Markdown 和文本预览及相关异常边界。          |
| [src/features/workspace/WorkspaceBrowserPage.test.tsx](src/features/workspace/WorkspaceBrowserPage.test.tsx)             | 验证管理按需加载的目录树、目录分页、路径定位和文件预览请求及相关异常边界。             |
| [src/i18n.test.ts](src/i18n.test.ts)                                                                                     | 验证语言初始化、切换和 URL 与存储持久化。                                              |
| [src/locales.test.ts](src/locales.test.ts)                                                                               | 校验两种语言的键、插值和界面动态文案约定。                                             |
| [src/playground/runtime.test.ts](src/playground/runtime.test.ts)                                                         | 验证实现浏览器内的 Job 查询、文件预览、删除、依赖图和静态任务事件协议及相关异常边界。  |
| [src/shared/ReplicaNotice.test.tsx](src/shared/ReplicaNotice.test.tsx)                                                   | 验证呈现副本来源、采样覆盖、遗漏文件和快照新鲜度及相关异常边界。                       |
| [src/shared/api/artifacts.test.ts](src/shared/api/artifacts.test.ts)                                                     | 验证产物路径、大小和修订边界。                                                         |
| [src/shared/api/client.test.ts](src/shared/api/client.test.ts)                                                           | 验证AxonXClient 统一传输、令牌、目标 Job 调用、事件流和目录查询及相关异常边界。        |
| [src/shared/api/event.test.ts](src/shared/api/event.test.ts)                                                             | 验证解码 SSE 帧，分派类型化事件并要求终止结果及相关异常边界。                          |
| [src/shared/hooks/useAsyncResource.test.tsx](src/shared/hooks/useAsyncResource.test.tsx)                                 | 验证对应模块的行为及相关异常边界。                                                     |
| [src/shared/hooks/useChart.test.tsx](src/shared/hooks/useChart.test.tsx)                                                 | 验证图表更新复用实例，并在卸载时释放实例和观察器。                                     |
| [src/shared/hooks/useCopyFeedback.test.tsx](src/shared/hooks/useCopyFeedback.test.tsx)                                   | 验证对应模块的行为及相关异常边界。                                                     |
| [src/shared/hooks/useRefresh.test.tsx](src/shared/hooks/useRefresh.test.tsx)                                             | 验证对应模块的行为及相关异常边界。                                                     |
| [src/shared/lib/format.test.ts](src/shared/lib/format.test.ts)                                                           | 验证统一日期、字节、数字、百分比、表格值及日期输入格式及相关异常边界。                 |
| [src/shared/lib/polling.test.ts](src/shared/lib/polling.test.ts)                                                         | 验证提供可取消、页面可见时运行且不重叠的轮询计时器及相关异常边界。                     |
| [src/shared/lib/replica.test.ts](src/shared/lib/replica.test.ts)                                                         | 验证副本产物过滤和实际修订替换。                                                       |
| [src/shared/lib/upstreamTasks.test.ts](src/shared/lib/upstreamTasks.test.ts)                                             | 验证上游任务数组的读取、拒绝无效值和引用隔离。                                         |
| [src/shared/schema/values.test.ts](src/shared/schema/values.test.ts)                                                     | 验证定义 JSON Schema 与表单值，处理类型、默认值、转换和字段错误及相关异常边界。        |
| [src/shared/ui/Select.test.tsx](src/shared/ui/Select.test.tsx)                                                           | 验证提供键盘可访问的选择器和原生表单适配及相关异常边界。                               |
| [src/features/tasks/execution.test.ts](src/features/tasks/execution.test.ts)                                             | 验证参数编码、跨页面连接、远程目标、失败与断流处理、重跑身份和停止操作。               |
| [src/shared/ui/SchemaForm.test.tsx](src/shared/ui/SchemaForm.test.tsx)                                                   | 验证字符串数组逐项增删与类型转换，以及复杂数组保持 JSON 输入。                         |
| [src/shared/api/workspace.test.ts](src/shared/api/workspace.test.ts)                                                     | 验证原文读取保留 frontmatter、注释、换行和 UTF-8 边界，并正确绑定远程目标。            |

### 样式

| 文件                                                   | 能力                                          |
| ------------------------------------------------------ | --------------------------------------------- |
| [src/styles/agent.css](src/styles/agent.css)           | 会话侧栏、对话、消息块和输入区。              |
| [src/styles/api.css](src/styles/api.css)               | API 目录、调用参数和结果面板。                |
| [src/styles/components.css](src/styles/components.css) | 按钮、通用表格、表单、索引和共享布局。        |
| [src/styles/home.css](src/styles/home.css)             | 首页研究流程和品牌内容。                      |
| [src/styles/index.css](src/styles/index.css)           | 声明样式依赖和加载顺序。                      |
| [src/styles/operations.css](src/styles/operations.css) | 在线及校验工作台、阶段、报告和日志布局。      |
| [src/styles/research.css](src/styles/research.css)     | 研究输出、因子、训练、回测及策略比较。        |
| [src/styles/reset.css](src/styles/reset.css)           | 统一浏览器默认样式和基础文档行为。            |
| [src/styles/runtime.css](src/styles/runtime.css)       | 机器资源、环境、服务更新和设置弹窗。          |
| [src/styles/select.css](src/styles/select.css)         | 共享选择器的触发、浮层和选项状态。            |
| [src/styles/shell.css](src/styles/shell.css)           | 顶部栏、导航、路径选择器和移动端外壳。        |
| [src/styles/stock.css](src/styles/stock.css)           | 股票信号、报告表格、质量、修订与 Top N 对比。 |
| [src/styles/tasks.css](src/styles/tasks.css)           | 任务列表、详情、步骤、日志和依赖图。          |
| [src/styles/tokens.css](src/styles/tokens.css)         | 定义深浅主题的颜色、字体及图表设计变量。      |
| [src/styles/workspace.css](src/styles/workspace.css)   | 文件树、文件预览、结构化数据和文件分页。      |

### 配置、文档和资产

| 文件                                           | 能力                                           |
| ---------------------------------------------- | ---------------------------------------------- |
| [src/locales/en.json](src/locales/en.json)     | 英文界面文案，包含静态和动态业务标签。         |
| [src/locales/zh.json](src/locales/zh.json)     | 与英文键一致的简体中文界面文案。               |
| [.gitignore](.gitignore)                       | 排除依赖、构建、缓存和本地环境文件。           |
| [index.html](index.html)                       | 提供挂载容器、元信息，并在首次绘制前应用主题。 |
| [package.json](package.json)                   | 声明前端依赖、构建、检查与发布脚本。           |
| [package-lock.json](package-lock.json)         | 固定 npm 依赖解析结果。                        |
| [vite.config.ts](vite.config.ts)               | 配置构建、演示资源前缀和后端开发代理。         |
| [eslint.config.js](eslint.config.js)           | 配置 TypeScript、React Hooks 和热更新检查。    |
| [tsconfig.json](tsconfig.json)                 | 组合应用和构建配置的 TypeScript 工程。         |
| [tsconfig.app.json](tsconfig.app.json)         | 启用前端严格类型、未使用声明和 JSX 检查。      |
| [tsconfig.node.json](tsconfig.node.json)       | 配置 Vite 构建配置的类型检查。                 |
| [pyproject.toml](pyproject.toml)               | 声明 Studio 静态资源 Python 包及打包规则。     |
| [**init**.py](__init__.py)                     | 向后端提供 Studio 构建产物目录。               |
| [LICENSE](LICENSE)                             | Apache 2.0 许可文本。                          |
| [README.md](README.md)                         | 英文安装、运行、协议和开发说明。               |
| [README_ZH.md](README_ZH.md)                   | 中文使用说明、架构约定和逐文件职责。           |
| [public/axonx-icon.svg](public/axonx-icon.svg) | 应用图标及 Agent 品牌标记。                    |
| [public/axonx-logo.svg](public/axonx-logo.svg) | 首页品牌字标。                                 |
