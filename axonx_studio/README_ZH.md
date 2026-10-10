# AxonX Studio

[English](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/README.md) · 简体中文

AxonX Studio 是 [AxonX](https://github.com/FlowLLM-AI/AxonX/blob/main/README_ZH.md) 的浏览器工作台：通过 Agent 开发研究插件，在选定服务提交 Task，查看日志、产物与图表。后端负责执行任务，插件提供研究算法。

![AxonX Studio 主页](https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/docs/figures/studio/home.png)

首页截图使用静态 Playground 的英文界面，数据与执行均为模拟。

## 主要功能

| 功能           | 能力                                                                                 |
| -------------- | ------------------------------------------------------------------------------------ |
| 任务提交       | 浏览已安装的 Task 定义，根据 JSON Schema 生成配置表单，填写上游 Task ID。            |
| 任务管理       | 筛选运行记录、查看参数与输出、跟踪进度和日志、查看上游关系、取消任务及删除选中运行。 |
| 机器管理       | 切换本机与已配置的远程目标，查看 CPU、内存、GPU 和运行环境信息。                     |
| 工作区         | 浏览配置的整个工作区，支持目录按需加载、目录分页与文件预览，包括 Parquet 分页预览。  |
| 研究结果       | 查看 ETL 数据集、因子指标、训练配置与曲线、预测产物。                                |
| 回测与策略比较 | 查看收益曲线、质量指标、持仓和年/季/月汇总，在共同日期区间比较两个回测。             |
| Agent          | 流式展示回答与工具调用、续接会话、重命名/标签/分叉/删除会话，以及停止当前轮次。      |
| API 调试       | 浏览当前机器的 Job 目录，通过 Schema 表单调用 API。                                  |

界面支持英文与简体中文、明暗主题，并保存浏览器偏好。Hash 路由保留所选机器与资源，例如 `#local/task-defs/catalog/demo`。

## 安装与启动

使用已激活的 Python 环境，要求 **Python 3.12+**。本地 Task 执行支持 macOS 和 Linux。预构建 Studio 包无需 Node.js 或本地前端构建。

```bash
pip install "axonx[studio]"
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

打开 <http://127.0.0.1:1024/>，在 **设置 → 本机服务令牌**（英文界面为 **Settings → Local service token**）输入相同 token 并应用。Studio 将 token 保存在浏览器 local storage 中，通过 Bearer token 验证 API 请求。可在同一设置表单中替换或清除 token。

也可以在启动 AxonX 的目录中创建 `.env`，设置 `AXONX_SERVICE_TOKEN`。CLI 自动加载该文件，已有环境变量优先。可选的服务商配置见 [example.env](https://github.com/FlowLLM-AI/AxonX/blob/main/example.env)。

如果已经安装 AxonX，可单独添加 Studio：

```bash
pip install axonx-studio
```

安装后重启服务。AxonX 通过包中的 `static_dir()` 加载 `dist/`，在启用 `service.web_enabled` 时将界面托管到 `/`。

### 运行第一个任务

1. 将机器选择器保持为 **Local**，进入 **Submit task**（提交任务）。
2. 在 **Native tasks** 中选择内置的 `demo` Task。
3. 将 `X` 设为 `2`、`Y` 设为 `3`，`Fail` 保持 `False`。
4. 点击 **Submit run**，进入 **Task management**（任务管理）并选择该运行。
5. 查看状态、步骤、日志、配置和最终输出。

将 **Task Name** 留空，可为每次实验生成名称。复用固定名称会替换已结束运行的目录。上游关系用于记录任务血缘，关系图不会自动执行依赖任务。

### 可选的研究与 Agent 配置

- **研究插件：** 在执行服务的 Python 环境安装 `axonx-qlib-a158`、`axonx-qlib-factor` 或 `axonx-qlib-strategy`，然后重启服务。研究视图需要已完成的运行及标准 `metadata.json` 和产物输出。
- **Tushare 下载：** 在后端配置 `AXONX_TUSHARE_TOKEN`。仅在使用兼容的自定义接口时覆盖 `AXONX_TUSHARE_BASE_URL`。
- **Agent：** 按服务商要求在后端配置 `CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL` 和 `CLAUDE_CODE_MODEL_NAME`。普通 Task 无需模型凭据即可运行。停止 Agent 当前轮次不会取消它已提交的 Task。
- **远程机器：** 配置后端服务的 `targets`，然后在 Studio 中选择目标。浏览器向本机服务认证，后端解析远程地址与凭据，通过 `target` 转发请求。

详见[研究环境准备](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/research/workflow.md)、[Agent 配置](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/agent/configuration.md)与[远程机器](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/guides/remote-machines.md)。

### 使用 Agent 研究

将研究问题和 [AxonX Skill](https://github.com/FlowLLM-AI/AxonX/blob/main/skills/axonx/SKILL.md) 交给外部或内置 Agent。内置开发需要配置源码访问与文件／命令工具，详见 [Agent 配置](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/agent/configuration.md)。先开发插件，再安装到选定服务，最后提交 Task，并等待上游成功。

Qlib Alpha158 参考流程为 **ETL → 训练 → 预测 → 回测**，因子分析从 ETL 独立分支。`qlib_a158`、`qlib_factor` 与 `qlib_strategy` 分别提供基线、可选因子和组合策略。比较运行时，保留代码、数据、窗口、参数、成本及 Task/Run ID。详见[研究流程](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/research/workflow.md)。

## npm 分发与静态托管

npm 包提供构建后的前端资源：

```bash
npm install @flowllm-ai/axonx-studio
```

使用静态服务器托管 `node_modules/@flowllm-ai/axonx-studio/dist/`，同时提供 AxonX 后端。前端使用相对于当前源的 API URL，因此需将同源的 `/health`、`/jobs`、`/files`、`/mcp` 和 `/proxy` 代理到后端。代理应保留 Authorization 请求头并支持 SSE 流式传输，以展示实时日志和 Agent 回答。页面使用 Hash 路由，无需为各个 Studio 页面配置服务端路由。

使用 AxonX 内置托管时，安装 Python 包即可。

## 源码开发

根据 `package.json`，前端工具链要求 **Node.js 22.x ≥ 22.13.0、24.x 或 26+**。从仓库根目录安装后端及开发依赖：

```bash
pip install -e '.[dev]'
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
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

| 路径                                                | 职责                                                                          |
| --------------------------------------------------- | ----------------------------------------------------------------------------- |
| `src/app/`                                          | Hash 路由、导航、机器选择、共享应用状态和页面懒加载。                         |
| `src/features/`                                     | 任务、运行中心、机器、Agent、工作区、研究、回测、策略比较与 API 页面。        |
| `src/shared/api/`                                   | 带认证的 Job 请求、响应解包、SSE 解析和共享 API 类型。                        |
| `src/shared/schema/` 与 `src/shared/ui/SchemaForm/` | JSON Schema 字段渲染与表单值转换。                                            |
| `src/shared/hooks/` 与 `src/shared/lib/`            | 异步资源、轮询、复制反馈、格式化和错误处理工具。                              |
| `src/locales/` 与 `src/i18n.ts`                     | 中英文翻译和语言偏好保存。                                                    |
| `src/styles/`                                       | 设计变量、布局、主题与业务样式。                                              |
| `src/webmcp.ts`                                     | 在浏览器提供 `document.modelContext` 时，注册列出和提交本机 Task 的可选工具。 |
| `public/`、`dist/`                                  | 源静态资源与生成的构建产物。                                                  |
| `__init__.py`、`pyproject.toml`、`package.json`     | Python 资源定位及 Python/npm 打包配置。                                       |

通过 `axonx.invoke` 或 feature API 封装调用 Job。请求使用 `{ arguments, target }`，客户端校验 Job 响应外层并返回 `answer`。各业务 API 应传递所选 `target` 和取消信号，流式调用复用共享 SSE 解析器。

新增页面时，在 `src/app/routes.ts` 注册路由，在 `navigation.ts` 注册导航，在 `PageOutlet.tsx` 接入渲染。用户可见文本需同步写入两份 locale。扩展步骤见 [Studio 开发](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/development/studio.md)。

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

工作区预览使用相对于执行工作区的路径。`/files` API 用于暂存上传与清理，完整产物需从执行机器的工作区取得。删除运行或工作区条目会删除对应数据，下游结果不会自动重建。

## 文档与许可证

- [Studio 入门](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/getting-started/studio.md)
- [任务管理](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/guides/task-management.md)
- [研究产物协议](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/reference/research-artifacts.md)
- [SSE 事件协议](https://github.com/FlowLLM-AI/AxonX/blob/main/docs/zh/api/events.md)
- [贡献指南](https://github.com/FlowLLM-AI/AxonX/blob/main/CONTRIBUTING_ZH.md)

采用 [Apache License 2.0](https://github.com/FlowLLM-AI/AxonX/blob/main/axonx_studio/LICENSE)。
