# 扩展 Studio

本页说明如何在现有 Studio 中增加页面、表单或图表。后端 Task、Step、Job 的扩展见 [开发指南](../dev_guide.md)；首次运行见 [Studio 入门](../getting-started/studio.md)。

## 开发环境

在仓库根目录启动服务，再在另一个终端运行前端：

```bash
cd axonx_studio
npm ci
npm run dev
```

完整开发工具链需要 Node.js 22.13+（22.x）、24.x 或 26+，以满足锁定的 Vite、ESLint 和 Vitest 依赖。Vite 默认监听 4173，开发代理默认连接 `http://127.0.0.1:1024`。可通过 `AXONX_DEV_SERVER` 指向另一个后端；修改后重启 Vite。代理覆盖 `/health`、`/jobs`、`/files`、`/mcp` 和 `/proxy`。

`npm run build` 先执行 TypeScript 检查，再输出 `dist`。从仓库根目录执行 `pip install ./axonx_studio`，AxonX 即可通过 Python 包加载这些资源。开发服务器用于热更新。

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

![Studio 功能地图](../../figures/getting-started/studio-map.svg)

## 增加页面

路由格式为 `#<machineId>/<section>/<view>/<resource>`。例如 `#local/task-defs/catalog/demo` 表示本机 demo 提交表单。`routeHash` 负责编码资源标识，`parseHash` 负责解码；不要手工拼接包含 `#` 的 Task ID。

1. 在 `features/<feature>` 中创建页面和必要的类型、API 封装。
2. 在 `app/routes.ts` 注册 section 与默认 view。
3. 在 `app/navigation.ts` 添加导航项。
4. 在 `app/PageOutlet.tsx` 接入页面分派，并传递选中的机器。
5. 将用户可见文本写入两份 locale，并同步维护 `docs/zh` 与 `docs/en` 中对应的文档正文。

区分页面路由状态与临时 UI 状态。可分享的资源选择适合放在 Hash 中；展开面板、加载进度等留在组件状态。无效 section 会回到首页。

## 调用后端

统一通过 `shared/api/client.ts` 的 `axonx.invoke` 或现有 feature API 封装调用 Job：

```typescript
const definitions = await axonx.invoke(
  "list_installed_task_definitions",
  {},
  { target: selectedMachine, signal: controller.signal },
);
```

请求体为 `{ arguments, target }`，响应外层为 JobResponse。客户端统一处理 HTTP 错误及 `success: false`，业务页面拿到解包后的 `answer`。返回数据类型应来自实际后端协议，不要通过强制类型断言掩盖协议差异。

机器选择必须贯穿列表、详情、提交和文件预览。同源 `/jobs` 请求携带浏览器设置中的服务 token；远程目标地址和凭据由后端解析。详见 [机器指南](../guides/remote-machines.md)。

## 表单与实时状态

优先复用 SchemaForm。整数与浮点数字段转为数字，枚举从 JSON 值解码，数组与对象输入为 JSON，可选空字段省略。没有默认值的可选布尔字段在关闭时也会省略。服务端仍负责最终校验。

需要取消过期请求时传入 AbortSignal。列表轮询复用 `usePolling`；长任务事件读取复用 SSE 解析器，不要把一次 Job 调用结束当成后台 Task 已完成。事件协议见 [实时事件](../api/events.md)。

Agent 工具卡片在参数流式生成时展示累积的 JSON 片段。收到完整工具消息后，在原卡片中更新格式化的输入并清除片段文本，因此命令在执行过程中持续可见，无需等待整轮结束后的历史记录刷新。

任务详情由任务配置、关系、运行详情和日志四张独立卡片组成，根据页面可用宽度显示两列或一列。每张卡片的内容区域都有高度上限，超出的内容可上下、左右滚动；日志保留原始行格式。

## 图表与文件

研究页面读取任务产物，新增计算沿用已明确的口径，并说明与插件汇总值的差异。训练曲线、收益率、持仓等字段来源见 [研究产物参考](../reference/research-artifacts.md)。缺失文件和空数据应有明确空状态。

文件预览保持工作区相对路径。`/files` 提供暂存上传与清理，不提供通用下载；完整产物需在执行机器工作区取得。不要将服务器绝对路径拼进公共界面。多图表页面注意容器 resize 与组件卸载时的资源释放。

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

`playground/runtime.ts` 维护任务与文件状态，`agent.ts` 维护脚本会话及工具消息，`stream.ts` 负责事件订阅清理，`catalog.ts` 声明支持的 Job。提交任务按经过时间推进，即使没有订阅者也会继续；状态查询和事件流同步这些状态。取消任务停止执行；AbortSignal 只关闭过期订阅并释放计时器。所有状态均保留统一 metadata，成功任务生成业务产物。`strategy` 选择合成结果，`outcome` 选择成功或失败，提交配置不会执行真实研究算法。

刷新或点击「重置示例」恢复初始状态，不持久化执行状态。测试覆盖数据契约、分页、生命周期、删除、事件流清理、脚本会话和网络隔离。应检查正式与 Playground 两种构建；站点验证会检查合并后的入口与资源路径。

## 应用运行页面

侧栏顺序为 **系统管理 → 日常运行 → 研究分析 → 开发工具**。系统管理包含全部任务、机器资源、运行环境；日常运行默认依次显示在线预测、比对、数据更新、同步。研究分析从智能体开始，随后按 ETL → 因子分析 → 模型训练 → 离线预测 → 离线回测 → 策略对比排列。开发工具包含提交任务、工作区、API 接口。系统管理和日常运行默认展开，其余默认收起；浏览器本地存储记住各组展开选择。进入页面（包括直接链接）时自动展开所属组，当前组仍可手动收起。应用可通过 `studio.pages` 的声明顺序调整业务入口顺序。

`default.yaml` 声明同步、数据更新、在线预测、比对四个通用入口。应用通过 `studio.pages` 关联具体调度并覆盖名称；AxonX 使用支持认证及远程目标的 `list_studio_pages` Job 提供配置。导航跟随当前机器，框架不硬编码插件的 Task 名称或调度名称。页面显示在 **日常运行** 分组，地址为 `#local/operations/<page-id>`。移除混合的 `online/runs` 路由；独立报告使用 `#local/report/task/<编码后的-task-id>`。

```yaml
studio:
  pages:
    downloads:
      title: { en: Data updates, zh: 数据更新 }
      view: tasks
      schedules: [daily_download]
      category: data_update
```

`view: schedules` 用于仅运行 Job 的调度（不允许 category；空 schedules 表示未配置同步调度）；`tasks` 展示 Task 进度、递归子任务及日志；`pipeline` 展示在线／比对报告。Task 页面必须选择 `TaskCategory`：`data_update`、`online_prediction` 或 `comparison`。插件类可声明 `category = TaskCategory.DATA_UPDATE`。分类与 `TaskType`、存储身份及 `report_kind` 独立，相同的复合执行类型可以属于不同页面。已安装定义、排队记录、运行记录及列表摘要均包含分类。没有分类的旧记录仍可在 **全部任务** 查看，重新执行后生成带分类的记录。复合子任务保留分类并记录 `parent_run_id`，页面索引只列顶层运行；手动和定时启动的顶层任务都可见。

不同调度分别展示，即使两个调度提交相同的 Task。点击调度按来源名称筛选其任务；**全部运行** 包括手动启动的任务。无效页面与服务不可用有明确的空／错误提示。切换机器或凭据会重新加载导航，导航每分钟刷新；页面、子任务进度及日志每五秒刷新，空闲时也会发现新任务。

Cron 调度器把执行状态和有限大小的结果原子写入 `workspace/schedules/<名称-sha256>.json`，保留全部正在运行的触发及最近 50 条已结束记录。超过 16 KiB 的结果改为截断摘要。服务重启后恢复已结束记录，未完成记录标记为取消并说明中断原因；scheduler_id 仍属于本次服务进程。调度页展示上次结果指标、错误、完成时间与近期触发详情。Job 执行成功表示 Job 已完成；提交的 Task 有独立生命周期。Task 记录与产物沿用既有持久化语义，同名重跑替换当前 Run。

在线报告展示实时采集、历史准备及定时模型预测；比对报告展示公共下载、各模型 ETL、在线来源检查、预测差异及回测。两者复用报告组件，使用独立的配置页面。子任务详情及可切换日志同时匹配 Task ID 与准确的 Run ID，被替换的运行不会冒充原运行。信号发布与任务执行状态分别展示。

运行 `npm run dev:playground`，打开 `http://localhost:4173/AxonX/playground/#local/operations/online` 可预览合成样例。同步、数据更新、晚间页面各自独立；Playground 刷新后重置，不演示磁盘持久化，也不执行插件算法。
