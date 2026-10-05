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

## 图表与文件

研究页面读取任务产物，新增计算沿用已明确的口径，并说明与插件汇总值的差异。训练曲线、收益率、持仓等字段来源见 [研究产物参考](../reference/research-artifacts.md)。缺失文件和空数据应有明确空状态。

文件预览保持工作区相对路径。`/files` 提供暂存上传与清理，不提供通用下载；完整产物需在执行机器工作区取得。不要将服务器绝对路径拼进公共界面。多图表页面注意容器 resize 与组件卸载时的资源释放。

## 验证与提交

```bash
npm run test
npm run lint
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

`playground/fixtures.ts` 创建虚拟工作区，包含 ETL → 因子分析 → 训练 → 预测 → 回测完整链路与两组回测。JSON 表格预览实现现有 Parquet 预览协议，无需附带 Parquet 解码器。收益与汇总指标由同一组序列生成。

`playground/runtime.ts` 维护任务与文件状态，`agent.ts` 维护脚本会话及工具消息，`stream.ts` 负责事件订阅清理，`catalog.ts` 声明支持的 Job。提交任务按经过时间推进，即使没有订阅者也会继续；状态查询和事件流同步这些状态。取消任务停止执行；AbortSignal 只关闭过期订阅并释放计时器。成功任务生成 metadata 与产物，失败或取消任务不会生成。`strategy` 选择合成结果，`outcome` 选择成功或失败，提交配置不会执行真实研究算法。

刷新或点击「重置示例」恢复初始状态，不持久化执行状态。测试覆盖数据契约、分页、生命周期、删除、事件流清理、脚本会话和网络隔离。应检查正式与 Playground 两种构建；站点验证会检查合并后的入口与资源路径。

## 在线链路

导航中的 **在线链路** 打开 `#local/online/runs`，汇总 API 采集、在线推理和预测比对任务（通过 `comparison_keys` 或 `comparisons` 识别），支持搜索、筛选与任务详情跳转。展示窗口覆盖率、输入超时、固定模型身份及比对指标。任务状态与窗口结果分别展示：报告任务完成时，也可能存在不完整窗口或单项比对异常。

页面复用现有同源 Job，保留所选机器 target。可见页面中的活跃任务每五秒刷新；页面或机器切换后清理过期请求和轮询。已完成任务读取 status result，运行中或失败任务通过分页工作区目录接口读取增量报告，包括尚未生成 metadata.json 的任务目录。空工作区和尚未发布报告各有空状态，请求失败提供错误信息与刷新操作。

无需 Python 或凭据即可预览：运行 `npm run dev:playground`，打开 `http://localhost:4173/AxonX/playground/#local/online/runs`。合成样例包含完整/部分/跳过采集、成功推理与输入超时、预测一致、源数据修订差异、协议不符及输入缺失。这些样例仅演示合同，不执行 a_stock 模型，也不代表迁移等价性已通过验证。
