# 扩展 Studio

本页说明如何在现有 Studio 中增加页面、表单或图表。后端 Task、Step、Job 的扩展见 [开发指南](../dev_guide.md)；首次运行见 [Studio 入门](../getting-started/studio.md)。

## 开发环境

在仓库根目录启动服务，再在另一个终端运行前端：

```bash
cd axonx_studio
npm ci
npm run dev
```

完整开发工具链需要 Node.js 22.13+（22.x）、24.x 或 26+，以满足锁定的 Vite、ESLint 和 Vitest 依赖。Vite 默认监听 4173，开发代理默认连接 `http://127.0.0.1:1024`。可通过 `AXONX_DEV_SERVER` 指向另一个后端；修改后重启 Vite。代理覆盖 `/health`、`/jobs`、`/upload`、`/mcp` 和 `/proxy`。

`npm run build` 先执行 TypeScript 检查，再输出 `dist`。从仓库根目录执行 `pip install ./axonx_studio`，AxonX 即可通过 Python 包加载这些资源。开发服务器用于热更新。

接口契约以 Python 模型和 `axonx/app/config/default.yaml` 为准。修改后运行 `npm run contracts:generate`，再运行 `npm run contracts:check`，更新 `src/shared/api/contracts.ts` 和 `src/playground/job-contracts.json`。修改 Python 来源，不直接编辑生成文件；导出的版本号也用于模拟机器信息。

如果运行期间已挂载的 Studio 构建资源被删除，页面请求返回 `503` 和恢复提示；缺失的静态资源请求返回 `404` 或 `503`。API 路由保持可用。可在原路径恢复构建资源；如果包安装路径发生变化，需要重启服务。本处理覆盖发送响应头之前的文件缺失，已经开始传输的响应无法替换。

## 目录职责

| 位置                | 职责                                              |
| ------------------- | ------------------------------------------------- |
| `src/app`           | Hash 路由、导航、机器选择、页面分派和共享应用状态 |
| `src/features`      | 提交、运行中心、Agent、研究和工作区等业务页面     |
| `src/shared/api`    | Job 请求、响应解包、SSE 和公共类型                |
| `src/shared/schema` | JSON Schema 的字段类型和表单值转换                |
| `src/shared/ui`     | SchemaForm、面板拖拽等复用组件                    |
| `src/shared/hooks`  | 异步加载、轮询和复制反馈                          |
| `src/styles`        | 设计变量、外壳和业务样式                          |
| `src/locales`       | 中文、英文翻译资源                                |

单选下拉统一使用 `src/shared/ui/Select.tsx`：`Select` 保留原生 option 写法、change 事件及表单校验；带内联标签的工具栏选择器可使用接受选项列表的 `Picker`。两者共用 `styles/select.css` 的主题样式、键盘导航及视口避让，不再新增可见的原生 select 或重复的菜单实现。

## 增加页面

路由格式为 `#<machineId>/<section>/<view>/<resource>`。例如 `#local/task-defs/catalog/demo` 表示本机 demo 执行表单。`routeHash` 负责编码资源标识，`parseHash` 负责解码；不要手工拼接包含 `#` 的 Task ID。

1. 在 `features/<feature>` 中创建页面和必要的类型、API 封装。
2. 在 `app/routes.ts` 注册 section 与默认 view。
3. 在 `app/navigation.ts` 添加导航项。
4. 在 `app/PageOutlet.tsx` 接入页面分派，并传递选中的机器。
5. 将用户可见文本写入两份 locale，并同步维护 `docs/zh` 与 `docs/en` 中对应的文档正文。

区分页面路由状态与临时 UI 状态。可分享的资源选择适合放在 Hash 中；展开面板、加载进度等留在组件状态。无效 section 会回到首页。

导航和页面标题由 `src/locales/{zh,en}.json` 提供，技术标识用于匹配路由、任务和报告：

| 中文入口 | 英文入口              | 路由 section / view     | 数据来源                                   |
| -------- | --------------------- | ----------------------- | ------------------------------------------ |
| 数据处理 | Data processing       | `etl/runs`              | `task_type: etl` 的研究产物                |
| 预测比对 | Prediction comparison | `operations/comparison` | `report_kind: compare_pipeline` 的运行报告 |
| 策略对比 | Strategy comparison   | `compare/strategies`    | 两份 `task_type: backtest` 的日度产物      |

数据处理的名称同时用于任务类型筛选和上下游依赖图；在线预测中的公共 ETL 环节显示为「公共数据处理」。预测比对导航和页面标题共用 `operations.comparison` 翻译项。

## 调用后端

统一通过 `shared/api/client.ts` 的 `axonx.invoke` 或现有 feature API 封装调用 Job：

```typescript
const definitions = await axonx.invoke(
  "list_task_defs",
  {},
  { target: selectedMachine, signal: controller.signal },
);
```

请求体为 `{ arguments, target }`，响应外层为 JobResponse。客户端统一处理 HTTP 错误及 `success: false`，业务页面拿到解包后的 `answer`。返回数据类型应来自实际后端协议，不要通过强制类型断言掩盖协议差异。

机器选择必须贯穿列表、详情、提交和文件预览。同源 `/jobs` 请求携带浏览器设置中的服务 token；远程目标地址和凭据由后端解析。详见 [机器指南](../guides/deployment.md#远程接入)。

## 表单与实时状态

优先复用 SchemaForm。整数与浮点数字段转为数字，枚举从 JSON 值解码，数组与对象输入为 JSON，可选空字段省略。没有默认值的可选布尔字段在关闭时也会省略。服务端仍负责最终校验。

需要取消过期请求时传入 AbortSignal。轮询复用共享的 `useRefresh` 调度器；长任务事件读取复用 SSE 解析器，不要把一次 Job 调用结束当成后台 Task 已完成。事件协议见 [实时事件](../api/events.md)。

Agent 工具卡片在参数流式生成时展示累积的 JSON 片段。收到完整工具消息后，在原卡片中更新格式化的输入并清除片段文本，因此命令在执行过程中持续可见，无需等待整轮结束后的历史记录刷新。

任务详情分为任务配置、关系、运行详情（默认选中）和日志四个 Tab，保留标题图标。切换 Tab 保留日志和报告控件状态。复用共享异步资源 Hook，在切换 Task 或机器时取消过期请求并隐藏上一项内容，迟到的取消响应也不能重新加载旧任务。运行详情中，普通 Task 仅展示步骤列表，子步骤缩进显示；复合 Task 仅展示直接子 Task 的状态和跳转入口，同一节点取最后一次调用，子任务详情进入其自身页面查看。业务报告、质量、文件及原始输出通过专门的报告页面查看。连续同名的已完成步骤默认合并折叠，展开可查看每条记录；完成与否以步骤状态为准，进度达到 100% 的运行中步骤仍显示为进行中。进行中或失败的步骤单独显示。各 Tab 的内容框填满屏幕剩余高度，超出内容在框内滚动，日志保留原始行格式。

## 图表与文件

研究页面读取任务产物，新增计算沿用已明确的口径，并说明与插件汇总值的差异。训练曲线、收益率、持仓等字段来源见 [研究产物参考](../reference/research-artifacts.md)。缺失文件和空数据应有明确空状态。

文件预览保持工作区相对路径。`/upload` 提供暂存上传与清理，不提供通用下载；完整产物需在执行机器工作区取得。不要将服务器绝对路径拼进公共界面。多图表页面注意容器 resize 与组件卸载时的资源释放。

## 验证与提交

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

根据修改选择相关测试；路由、Schema 值转换、事件解析和请求解包已有测试可扩展。界面检查至少包含英文与中文、空数据、加载失败、长文本和窄窗口。不要在截图中暴露 token、私人会话、任务标识或机器地址。

更新用户文档时同步补充功能入口、前置条件、步骤和失败处理。截图与 SVG 采用英文，截图中不包含凭据、私人路径或会话内容。

## 实现依据

- `axonx_studio/src/app/routes.ts`、`PageOutlet.tsx`、`navigation.ts`
- `axonx_studio/src/shared/api/client.ts`、`event.ts`
- `axonx_studio/src/shared/schema/values.ts`
- `axonx_studio/vite.config.ts`、`package.json`

## 静态 Playground

官网在 `/AxonX/playground/` 提供独立 Studio，复用正式应用的页面、Job 响应和 SSE 解析器。无需 Python 服务、数据库或 LLM；证券及研究结果均为合成数据，Agent 回复为脚本演示。

```bash
npm ci
npm run dev:playground
# 打开 http://localhost:4173/AxonX/playground/
npm run build:playground
```

`DOCS_BASE` 决定部署前缀，默认为 `/AxonX/`。独立的 `dist-playground/` 输出不会覆盖 Python 打包所用的普通 `dist/`。文档构建会生成 Playground 并合并到 Pages 发布产物。构建官网前，需要分别在 `axonx_studio/` 与 `github-pages/` 安装依赖。

所有请求（包括事件流）统一经过 `AxonXClient.request`。默认 transport 调用同源 HTTP；Playground 模式由 `main.tsx` 在挂载前注入 `createPlayground()`，该客户端禁用认证。业务 API 无需按模式分支。未知 Job、文件与远程 target 返回明确错误，不回退到网络请求。

`playground/fixtures.ts` 创建虚拟工作区，包含 ETL → 训练 → 预测 → 回测主链、从 ETL 独立分出的因子分析与两组回测。JSON 表格预览实现现有 Parquet 预览协议，无需附带 Parquet 解码器。收益与汇总指标由同一组序列生成。

`playground/runtime.ts` 维护任务与文件状态，`agent.ts` 维护脚本会话及工具消息，`stream.ts` 负责事件订阅清理，`catalog.ts` 从生成的服务 schema 中选择支持的 Job 并提供演示表单默认值。Task ID 使用 `type#registration#instance`，注册名与 metadata 对应，Agent 会话使用 UUID。提交命令在 CLI 事件连接打开期间推进；关闭连接会停止其拥有的模拟执行，与服务拥有的命令清理行为一致。关闭独立的 Task 观察只释放该订阅。所有状态均保留统一 metadata，成功任务生成业务产物。`strategy` 选择合成结果，`outcome` 选择成功或失败，提交配置不会执行真实研究算法。

刷新或点击「重置示例」恢复初始状态，不持久化执行状态。测试覆盖数据契约、分页、生命周期、删除、事件流清理、脚本会话和网络隔离。应检查正式与 Playground 两种构建；站点验证会检查合并后的入口与资源路径。

## 应用运行页面

`features/operations/pages.ts` 按 `reportKinds` 定义分组：在线预测对应 `online_pipeline`/`online`，预测比对对应 `compare_pipeline`，数据更新对应 `data_update`。页面读取当前 Task metadata 和报告，不提供调度控制/历史记录。新增报告应由生产 Task 声明 `report_kind`，并实现有类型的报告和产物契约；生命周期继续使用共享执行/详情视图。

Task 执行由 features/tasks/execution.ts、TaskExecution.tsx 管理，连接所有权独立于页面选择，调用 cli argv、核验进程结果、观察 metadata 并比较 started_at。应与 Schema 表单编辑和所选导航路由分离。
