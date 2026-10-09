# AxonX 文档站点

[English](README.md) · 简体中文

本目录维护 AxonX 静态文档框架：VitePress 配置、Vue 主题、内容生成、导出和构建验证。正文仍由 `docs/en/`、`docs/zh/` 与项目/插件 README 维护。浏览站点无需 AxonX 后端或 Python 环境。

默认部署地址为 <https://flowllm-ai.github.io/AxonX/>，语言路径为 `/en/` 和 `/zh/`。

## 阅读路径

站点分为六个导航区：**开始使用、量化研究、Agent、运行与部署、接口参考、开发扩展**。Studio 入门归入开始使用，研究插件归入量化研究，API 与配置归入接口参考。每个分区以总览串联目标与专题指南；Agent 读者先选择外部接入或内置会话。首页链接到 README Benchmark 和复现说明，不重复维护指标表。

[文档导航](../docs/zh/index.md)按目标提供阅读路径。项目与插件 README 维护概览与算法细节，指南链接到这些来源，避免重复维护实验数据表。每篇文档只有一个导航归属，可以跨区链接。

## 开发与验证

使用 Node.js 22+、npm 和完整仓库检出：

```bash
npm --prefix axonx_studio ci
cd github-pages
npm ci
npm run test
npm run dev
```

打开输出的地址，包括 `/AxonX/` 基础路径。开发命令先将原始内容生成到 `.generated/site/`，再启动 VitePress。修改原始正文、导航、框架模块或主题后，重启 `npm run dev` 刷新生成目录。

```bash
npm run build
npm run preview
```

构建会生成内容、创建 `dist/` 并校验输出。预览仅浏览已有构建，两个命令都不部署。站点继续提供本地搜索、语言与外观偏好、页内目录、原始文件编辑链接和逐页 Markdown 导出。

| 命令                   | 用途                                            |
| ---------------------- | ----------------------------------------------- |
| `npm run content`      | 校验内容目录并重新生成构建输入                  |
| `npm run test`         | 检查目录、设置、链接、语言优先级与翻译键一致性  |
| `npm run dev`          | 生成内容并启动开发服务器                        |
| `npm run build`        | 生成、构建并验证 HTML、导航、资源、锚点和导出   |
| `npm run preview`      | 浏览已有生产产物                                |
| `npm run format:check` | 用 Prettier 检查框架、docs 和根目录/插件 README |
| `npm run format`       | 格式化这些原文，提交前检查差异                  |

生成文件、依赖、锁文件与构建输出通过仓库[忽略规则](../.prettierignore)排除格式化。不要手动修改 `.generated/` 或 `dist/`。

## 源码职责

| 位置                                             | 职责                                                         |
| ------------------------------------------------ | ------------------------------------------------------------ |
| `../docs/en/`、`../docs/zh/`、`../docs/figures/` | 双语原文与共用图片                                           |
| `../docs/.vitepress/navigation.mjs`              | 阅读顺序、分组入口和唯一页面归属                             |
| `site/config.mts`                                | VitePress 语言、导航、搜索、元信息和构建钩子                 |
| `site/theme/`                                    | 首页、文档工具、偏好控件与样式                               |
| `lib/site-model.mjs`                             | 发现双语原文、映射导入 README 并校验内容目录                 |
| `lib/headings.mjs`                               | 提取代码围栏外的标题，提供导入概览页标题                     |
| `lib/settings.mjs`                               | 校验部署基础路径和站点 origin                                |
| `lib/links.mjs`                                  | 转换围栏示例之外的文档链接                                   |
| `lib/exports.mjs`                                | 按语言与导航分组顺序生成 Markdown 和 LLM 导出                |
| `scripts/generate-content.mjs`                   | 装配原文、框架、路由映射与共用资源                           |
| `scripts/verify-build.mjs`                       | 校验 HTML、导航、锚点、原文链接与导出                        |
| `tests/`                                         | 构建模块的针对性回归测试                                     |
| `.generated/site/`                               | 可重新生成的 VitePress 输入，包括 `.source-map.json`         |
| `dist/`                                          | 可部署的 HTML、资源、Markdown、`llms.txt` 和 `llms-full.txt` |

主题文案与 VitePress 界面标签统一维护在 `site/theme/locales/en.json` 和 `zh.json`，测试检查两份资源的键一致。`i18n.ts` 提供响应式语言资源与站内链接；`language.mjs` 负责语言选择与路由转换；`home.ts` 保存与语言无关的首页元数据。参考 Studio 将语言资源与功能代码分离的结构，响应式能力直接使用 Vue/VitePress，无需额外翻译依赖。Markdown 原文与导航标签继续维护在 `docs/`。

框架文件从 `docs/.vitepress/` 移至 `site/` 和 `lib/`，导航仍与内容放在一起。已有文档 URL 保留。早期的 `getting-started/introduction` 和 `guides/plugin-management` 路由仍不生成，也不提供重定向。

### 新增页面

1. 添加路径相同的中英文 Markdown，使用一级标题。
2. 在 [navigation.mjs](../docs/.vitepress/navigation.mjs) 中按阅读顺序注册一次路由。
3. 从相关目标或指南链接到新页面；阅读路径变化时更新两份文档导航。
4. 运行测试、构建与格式检查，预览双语及受影响的窄屏、主题。

内容目录会在替换生成输出之前拒绝双语路径不一致、未归属页面、重复归属、导入路由冲突、缺失原文与缺失标题。根目录和插件 README 通过 `lib/site-model.mjs` 映射为 `getting-started/overview`、`development/contributing`、`plugins/alpha158` 和 `plugins/qlib-factor`；`docs/{lang}/index.md` 对应 `{lang}/docs`。

### 链接与导出

链接相对原始文件解析。已发布原文转换为站内路由，共用图片转换为 `public/media/<仓库路径>`，未发布仓库文件链接到 GitHub。转换 Markdown 行内链接与 HTML 链接，保留围栏代码示例。标题提取排除围栏代码注释；以标志开头的项目 README 在生成时补充一级标题，不修改原文。语言选择依次遵循 `?lang=en|zh`、显式 `/en/` 或 `/zh/` 路由、与 Studio 共用的 `language` 偏好、浏览器语言（中文或默认英文）。根页面先渲染英文，再由浏览器跳转到所选语言的首页。保存的偏好不会覆盖显式语言路由。自动语言跳转替换当前浏览历史记录；站内导航及浏览器前进／后退后也会应用语言选择。顶栏切换英文／中文和浅色／深色；切换语言保留当前文档、查询参数和锚点，并更新已有的 `lang` 参数。旧的 `axonx-language` 偏好不再读取。默认浅色；旧的跟随浏览器／系统偏好不再跟随浏览器或系统设置。

原文映射保证编辑链接指向真实维护位置。Markdown 导出使用绝对 URL 与 UTF-8 BOM。`llms.txt`、`llms-full.txt` 按站点相同的双语导航顺序排列。未导入站点的历史实验材料继续链接到仓库原文。

## 部署

[文档工作流](../.github/workflows/docs.yml)安装依赖，运行模块测试并构建，再上传 `dist/` 到 GitHub Pages。PR 仅验证，匹配的 push 或 `main` 分支手动运行可部署。GitHub Pages 来源需设置为 GitHub Actions。

| 变量            | 默认值                         | 含义                                              |
| --------------- | ------------------------------ | ------------------------------------------------- |
| `DOCS_BASE`     | `/AxonX/`                      | 部署路径，保留首尾斜线                            |
| `DOCS_SITE_URL` | `https://flowllm-ai.github.io` | 导出使用的 HTTP(S) origin，不包含路径、查询或凭据 |

自定义域名部署在根路径时：

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run build
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run preview
```

CI 使用相同变量，并在 GitHub Pages 设置域名和 DNS。构建检查验证本地产物，不验证外部链接或线上部署。

### Clone 徽章

文档工作流每天在 UTC 02:17（北京时间 10:17）以及文档部署时更新 `/badges/clones.json`。根目录 README 通过此公开 Shields 端点展示 GitHub 滚动最近 14 天的 Clone 总次数（不是独立克隆者人数）。只公开汇总次数，不发布 Token 或每日流量记录。

在仓库 Actions Secret 中配置 `AXONX_TRAFFIC_TOKEN`：使用仅限本仓库、具有 **Administration: read** 权限的专用 fine-grained PAT。随后在 `main` 上手动运行 **CI / Documentation** 初始化徽章。未配置 Secret 时显示 `not configured`；API 请求失败会终止构建并保留上次部署。请在 Token 到期前更新 Secret。本地验证可运行 `node --test .github/scripts/write-traffic-badge.test.mjs`。

### Vercel

仓库根目录的 [`vercel.json`](../vercel.json) 将文档和 Playground 部署为静态站点。配置选择 **Other** 框架预设，避免仓库的 Python 依赖触发 FastAPI 入口检测，安装两个前端包，并发布 `github-pages/dist`。

Vercel 的 **Root Directory** 保持为仓库根目录，在 Project Settings 中选择 **Node.js 22.x**，并保持 **Automatically expose System Environment Variables** 开启。构建使用 `DOCS_BASE=/`，`DOCS_SITE_URL` 默认取 `https://$VERCEL_PROJECT_PRODUCTION_URL`；可显式设置 `DOCS_SITE_URL` 覆盖正式站点 origin。预览构建的 导出 URL 也使用正式站点 origin。这些配置不改变 GitHub Pages 工作流，也不部署 AxonX 研究后端。

安装两个包后，可从仓库根目录验证 Vercel 构建：

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://axon-x.vercel.app npm --prefix github-pages run build
```

## 排障

| 现象               | 处理                                         |
| ------------------ | -------------------------------------------- |
| 开发时修改未出现   | 重启 `npm run dev` 重新生成原文              |
| 内容目录校验失败   | 检查双语路径、导航归属、导入路由和标题       |
| 站内链接或锚点失败 | 从原文解析地址，核对目标页面标题             |
| 部署后资源失败     | 对齐 `DOCS_BASE` 与部署路径并重新构建        |
| 导出使用错误域名   | 设置 `DOCS_SITE_URL` 并重新构建              |
| 页面切换语言       | 依次检查 `?lang`、语言路由与 Studio 共用偏好 |
| 构建成功但未部署   | 检查事件、分支、Pages 来源、环境和工作流权限 |

仓库贡献要求见[贡献指南](../CONTRIBUTING_ZH.md)。

官网导航与首页提供 Playground 入口。`npm run build` 同时构建 Studio 的浏览器模拟模式，并将独立产物合并到 `dist/playground/`。开发文档站时，可另开终端运行 `npm --prefix axonx_studio run dev:playground` 预览演示；完整合并站点通过 build 与 preview 检查。无需后台服务。

## 内容与图示维护约定

中英文文档按相同文件路径和章节组织，截图与示意图共用 `docs/figures/` 中的资源。

根目录与插件 README 在构建时导入，双语正文仍在仓库根目录与各插件目录维护。导航由 `docs/.vitepress/navigation.mjs` 定义。

阅读路径分为开始使用、量化研究、Agent、运行与部署、接口参考和开发扩展。`docs/en/index.md` 与 `docs/zh/index.md` 提供选路入口；入门教程完成最小流程，操作指南解决具体任务，参考页定义契约，概念页解释执行与记录。

站点框架位于 `github-pages/site/`，构建模块位于 `github-pages/lib/`，入口脚本位于 `github-pages/scripts/`。`docs/` 维护正文与共用图片，`docs/.vitepress/navigation.mjs` 维护页面归属。

图片按解释的主题存放在 `docs/figures/` 中。每页使用直接回答本页问题的图示；协议总览不能代替会话、机器路由或安装流程。

| 目录                    | 职责                                             |
| ----------------------- | ------------------------------------------------ |
| `getting-started/`      | 产品总览、首次执行、Studio 导航                  |
| `concepts/`             | 框架架构、Job/Task 边界、生命周期、工作区、血缘  |
| `agent/`                | 独立接入路径、外部开发、内置证据阅读与配置       |
| `research/`             | 研究依赖、证据阅读、记账、对齐比较、实验确认     |
| `api/`                  | 协议契约与任务、会话、机器、文件、插件及同步调用 |
| `guides/`, `reference/` | 运维流程与配置、扩展契约                         |
| `plugins/`              | 算法特定的特征组成                               |
| `benchmark/`            | 标明来源、窗口与指标定义的历史量化结果           |
| `studio/`               | 作为界面证据的真实截图                           |

概念图与指标图使用 SVG，截图使用 PNG。双语页面共用图示，周边说明与替代文本分别翻译。保持根目录 README 的图片路径稳定。总览介绍产品，架构解释实现，血缘描述已记录的引用，工作流描述显式研究阶段，实验图解释筛选与独立确认。

使用统一手写字体栈（`Comic Sans MS`、`Chalkboard SE`、`Comic Neue`、cursive）、清晰标签以及 SVG `title` / `desc` 无障碍元数据。外框使用实线圆角，卡片或辅助线使用虚线，保留各图原有配色。标题与副标题建立明确层级，宽卡片正文左对齐，脚注与主图分开，连线避开标签。产品总览以研究插件、Task 执行与共享工作区三个模块组织，提交与查询路径连续连接到对应模块。减少嵌套标签框，简短列表在同一卡片内排版。箭头必须明确表达执行、数据依赖或记录查询。备选接入方式和独立配置来源不能画成串行阶段。因子分析从 ETL 分支；提交受理与 Task 成功分别表达。数据、插件与工作进程属于各自的执行目标环境。

更新图示时检查 SVG 渲染与文字边界、双语引用和完整站点构建。保留截图来源与基准数值；重画概念图不应虚构界面状态或重算历史指标。当前产品品牌资源由 `axonx_studio/public/` 维护；`docs/` 根层的 FlowLLM 标志是 `scripts/generate_flowllm_logo.py` 生成的历史组织素材。

每个导航区以按目标组织的总览为入口，调整阅读顺序时保留已有深层链接。站点为以标志开头的项目 README 补充生成的一级标题，不修改原文。
