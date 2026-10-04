# AxonX Documentation / AxonX 文档

- [English documentation](en/index.md)
- [中文文档](zh/index.md)

The English and Chinese documentation use matching file paths and sections. Screenshots and diagrams are shared under `figures/`.

中英文文档按相同文件路径和章节组织，截图与示意图共用 `figures/` 中的资源。

Root and plugin READMEs are imported at build time; their bilingual sources remain at the repository root and in each plugin directory. Navigation is defined in `.vitepress/navigation.mjs`.

根目录与插件 README 在构建时导入，双语正文仍在仓库根目录与各插件目录维护。导航由 `.vitepress/navigation.mjs` 定义。

## Content ownership / 内容职责

Reader journeys are organized as Get started, Research, Agent, Operations, Reference, and Developers. The document maps in `en/index.md` and `zh/index.md` explain where to begin. Tutorials complete a minimal workflow, how-to guides address a concrete task, references define contracts, and concept pages explain execution and records.

阅读路径分为开始使用、量化研究、Agent、运行与部署、接口参考和开发扩展。`en/index.md` 与 `zh/index.md` 提供选路入口；入门教程完成最小流程，操作指南解决具体任务，参考页定义契约，概念页解释执行与记录。

The site framework lives in `github-pages/site/`, with shared build modules in `github-pages/lib/` and entry scripts in `github-pages/scripts/`. Keep prose and shared figures here, and maintain page ownership in `.vitepress/navigation.mjs`. See the [site maintenance guide](../github-pages/README.md) for generation and validation.

站点框架位于 `github-pages/site/`，构建模块位于 `github-pages/lib/`，入口脚本位于 `github-pages/scripts/`。本目录维护正文与共用图片，`.vitepress/navigation.mjs` 维护页面归属。生成与验证方法见[站点维护指南](../github-pages/README_ZH.md)。

## Figures / 图示组织

Keep assets in `figures/` by the subject they explain. A page should use a diagram that answers its own question; a transport overview cannot substitute for a session, machine, or installation flow.

图片按解释的主题存放在 `figures/` 中。每页使用直接回答本页问题的图示；协议总览不能代替会话、机器路由或安装流程。

| Directory / 目录        | Responsibility / 职责                                                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `getting-started/`      | Product overview, first execution, Studio navigation / 产品总览、首次执行、Studio 导航                                                           |
| `concepts/`             | Framework architecture, Job/Task boundaries, lifecycle, workspace, lineage / 框架架构、Job/Task 边界、生命周期、工作区、血缘                     |
| `agent/`                | Independent access paths, external development, built-in evidence and configuration / 独立接入路径、外部开发、内置证据阅读与配置                 |
| `research/`             | Research dependencies, evidence reading, accounting, aligned comparisons, experiment confirmation / 研究依赖、证据阅读、记账、对齐比较、实验确认 |
| `api/`                  | Protocol contracts and specific Task, session, machine, file, plugin/sync flows / 协议契约与任务、会话、机器、文件、插件及同步调用               |
| `guides/`, `reference/` | Operational procedures and configuration/extension contracts / 运维流程与配置、扩展契约                                                          |
| `plugins/`              | Algorithm-specific feature composition / 算法特定的特征组成                                                                                      |
| `benchmark/`            | Historical quantitative results with sources, windows, and metric definitions / 标明来源、窗口与指标定义的历史量化结果                           |
| `studio/`               | Actual UI screenshots used as visual evidence / 作为界面证据的真实截图                                                                           |

Use SVG for conceptual diagrams and quantitative charts, and PNG for screenshots. Share diagrams between languages and translate their surrounding explanations and alt text. Keep root README image paths stable. The overview introduces the product; architecture explains implementation; lineage describes recorded references; workflow describes explicit research stages; experiments explains selection and independent confirmation.

概念图与指标图使用 SVG，截图使用 PNG。双语页面共用图示，周边说明与替代文本分别翻译。保持根目录 README 的图片路径稳定。总览介绍产品，架构解释实现，血缘描述已记录的引用，工作流描述显式研究阶段，实验图解释筛选与独立确认。

Use the shared hand-drawn font stack (`Comic Sans MS`, `Chalkboard SE`, `Comic Neue`, cursive), readable labels, and SVG `title` / `desc` accessibility metadata. Use solid rounded outer frames and dashed cards or guides; retain each diagram's existing palette. Use a clear title/subtitle hierarchy, left-align copy in wide cards, separate footnotes from the diagram, and keep connectors clear of labels. The product overview uses three pillars—research plugins, Task execution, and shared workspace—with continuous submission and query paths. Avoid excessive nested badges; short lists can share one card. Arrows must have a defined meaning: execution, data dependency, or reading records. Alternatives and independent configuration sources must not be drawn as sequential stages. Factor analysis branches from ETL; submission acceptance is separate from Task success. Show deployment-local data, plugins, and workers inside the execution target's boundary.

使用统一手写字体栈（`Comic Sans MS`、`Chalkboard SE`、`Comic Neue`、cursive）、清晰标签以及 SVG `title` / `desc` 无障碍元数据。外框使用实线圆角，卡片或辅助线使用虚线，保留各图原有配色。标题与副标题建立明确层级，宽卡片正文左对齐，脚注与主图分开，连线避开标签。产品总览以研究插件、Task 执行与共享工作区三个模块组织，提交与查询路径连续连接到对应模块。减少嵌套标签框，简短列表在同一卡片内排版。箭头必须明确表达执行、数据依赖或记录查询。备选接入方式和独立配置来源不能画成串行阶段。因子分析从 ETL 分支；提交受理与 Task 成功分别表达。数据、插件与工作进程属于各自的执行目标环境。

When updating figures, verify SVG rendering and text bounds, matching bilingual references, and the complete site build. Preserve screenshot provenance and benchmark values; conceptual redrawing is not a reason to fabricate UI states or recalculate historical metrics. `axonx_studio/public/` owns current product branding; the root FlowLLM logo files here are legacy organization artwork produced by `scripts/generate_flowllm_logo.py`.

更新图示时检查 SVG 渲染与文字边界、双语引用和完整站点构建。保留截图来源与基准数值；重画概念图不应虚构界面状态或重算历史指标。当前产品品牌资源由 `axonx_studio/public/` 维护；本目录根层的 FlowLLM 标志是 `scripts/generate_flowllm_logo.py` 生成的历史组织素材。

Each navigation area opens with a goal-based overview. Preserve existing deep links when improving reading order. The site imports the logo-led project README with a generated H1, without editing its source.

每个导航区以按目标组织的总览为入口，调整阅读顺序时保留已有深层链接。站点为以标志开头的项目 README 补充生成的一级标题，不修改原文。
