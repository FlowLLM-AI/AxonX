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
| `npm run test`         | 检查目录失败场景、部署设置与链接转换            |
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

框架文件从 `docs/.vitepress/` 移至 `site/` 和 `lib/`，导航仍与内容放在一起。已有文档 URL 保留。早期的 `getting-started/introduction` 和 `guides/plugin-management` 路由仍不生成，也不提供重定向。

### 新增页面

1. 添加路径相同的中英文 Markdown，使用一级标题。
2. 在 [navigation.mjs](../docs/.vitepress/navigation.mjs) 中按阅读顺序注册一次路由。
3. 从相关目标或指南链接到新页面；阅读路径变化时更新两份文档导航。
4. 运行测试、构建与格式检查，预览双语及受影响的窄屏、主题。

内容目录会在替换生成输出之前拒绝双语路径不一致、未归属页面、重复归属、导入路由冲突、缺失原文与缺失标题。根目录和插件 README 通过 `lib/site-model.mjs` 映射为 `getting-started/overview`、`development/contributing`、`plugins/alpha158` 和 `plugins/alpha158-enhanced`；`docs/{lang}/index.md` 对应 `{lang}/docs`。

### 链接与导出

链接相对原始文件解析。已发布原文转换为站内路由，共用图片转换为 `public/media/<仓库路径>`，未发布仓库文件链接到 GitHub。转换 Markdown 行内链接与 HTML 链接，保留围栏代码示例。标题提取排除围栏代码注释；以标志开头的项目 README 在生成时补充一级标题，不修改原文。首次访问遵循 URL 的语言，手动选择语言后保存偏好供后续访问使用。

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

## 排障

| 现象               | 处理                                         |
| ------------------ | -------------------------------------------- |
| 开发时修改未出现   | 重启 `npm run dev` 重新生成原文              |
| 内容目录校验失败   | 检查双语路径、导航归属、导入路由和标题       |
| 站内链接或锚点失败 | 从原文解析地址，核对目标页面标题             |
| 部署后资源失败     | 对齐 `DOCS_BASE` 与部署路径并重新构建        |
| 导出使用错误域名   | 设置 `DOCS_SITE_URL` 并重新构建              |
| 页面切换语言       | 检查保存的语言偏好                           |
| 构建成功但未部署   | 检查事件、分支、Pages 来源、环境和工作流权限 |

维护约定见[内容职责说明](../docs/README.md)和[贡献指南](../CONTRIBUTING_ZH.md)。
