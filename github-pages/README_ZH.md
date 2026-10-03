# AxonX 文档站点

[English](README.md) · 简体中文

本目录提供 AxonX 双语产品首页和文档站点的构建脚本。站点使用 VitePress 与自定义 Vue 主题，生成静态资源后发布到 GitHub Pages。构建或浏览文档无需 AxonX 后端或 Python 环境。

默认部署地址为 <https://flowllm-ai.github.io/AxonX/>，英文内容位于 `/AxonX/en/`，简体中文位于 `/AxonX/zh/`。

## 站点功能

- 双语产品首页，包含研究流程入口与 Studio 截图。
- 按文档、插件、量化研究、Studio、Agent 和开发者划分导航页签，每组提供对应的侧边目录。
- 本地搜索、页内目录、上一篇/下一篇，以及指向仓库原始文件的编辑链接。
- 保存语言偏好（英文、中文或跟随浏览器）与外观偏好（亮色、暗色或跟随系统）。
- 提供每页的 **查看 Markdown** 链接、`llms.txt` 文档索引和 `llms-full.txt` 合并文档。

## 本地开发

要求 **Node.js 22+** 与 npm。需使用完整的仓库检出，内容生成会读取本目录之外的文件。

```bash
cd github-pages
npm ci
npm run dev
```

打开 VitePress 输出的地址，包含 `/AxonX/` 基础路径。`dev` 先生成站点源码，再启动 VitePress，对生成目录中的改动提供热更新。修改原始正文、配置或主题后，停止并重新运行 `npm run dev`，以刷新复制的内容。

构建并预览生产产物：

```bash
npm run build
npm run preview
```

`preview` 仅浏览已有构建，不会重新生成或构建内容。这两个命令均不会部署站点。

| 命令（在 `github-pages/` 中执行） | 用途                                                                     |
| --------------------------------- | ------------------------------------------------------------------------ |
| `npm run content`                 | 根据原始文件重新生成 `.generated/site/`。                                |
| `npm run dev`                     | 生成内容并启动 VitePress 开发服务器。                                    |
| `npm run build`                   | 生成内容、构建到 `dist/` 并校验输出。                                    |
| `npm run preview`                 | 预览构建后的静态站点。                                                   |
| `npm run format:check`            | 用 Prettier 检查站点源码、`docs/`、根目录 README/贡献指南及插件 README。 |
| `npm run format`                  | 格式化同一组源文件。                                                     |

格式化命令也会处理 `github-pages/` 之外的文件。生成目录、构建产物、锁文件和依赖通过仓库的 [Prettier 忽略配置](../.prettierignore) 排除。

## 内容来源与路由

请修改原始源文件。`.generated/` 与 `dist/` 是可重新生成的构建目录，不纳入 Git。

| 站点路由（位于 `/en/` 或 `/zh/` 之后） | 原始源文件                                                                          |
| -------------------------------------- | ----------------------------------------------------------------------------------- |
| 语言首页                               | `docs/.vitepress/theme/HomePage.vue`；各语言入口页由脚本生成。                      |
| `docs`                                 | `docs/en/index.md` 或 `docs/zh/index.md`。                                          |
| `getting-started/overview`             | 根目录 `README.md` 或 `README_ZH.md`。                                              |
| `development/contributing`             | 根目录 `CONTRIBUTING.md` 或 `CONTRIBUTING_ZH.md`。                                  |
| `plugins/alpha158`                     | `plugins/a158/README.md` 或 `README_ZH.md`。                                        |
| `plugins/alpha158-enhanced`            | `plugins/a158_enhanced/README.md` 或 `README_ZH.md`。                               |
| 其他文档路由                           | `docs/en/` 与 `docs/zh/` 中路径匹配的 Markdown 文件，包括 `plugins/management.md`。 |

生成器写入 `.generated/site/.source-map.json`，记录各文档页对应的仓库源文件。VitePress 使用该映射生成原始文件编辑链接与 Markdown 导出。本目录的 README 介绍构建工具，不会作为站点文档页导入。

### 新增或更新页面

1. 修改页面的原始源文件，或在 `docs/en/` 与 `docs/zh/` 新增相同路径的文件。
2. 使用一级 `#` 标题，导航中的文档名称会从正文标题读取。
3. 在 [navigation.mjs](../docs/.vitepress/navigation.mjs) 中将新文档路由注册到且仅注册到一个分组。每个已注册路由都需有中英文源文件。
4. 图片放在 `docs/figures/` 等仓库共享位置，从原始正文链接到图片。
5. 运行 `npm run build` 与 `npm run format:check`，再预览受影响的中英文页面。

首页、布局与偏好设置在 `docs/.vitepress/theme/` 中维护。站点配置、搜索、元信息、部署路径与导出生成逻辑位于 [config.mts](../docs/.vitepress/config.mts)。

### 链接与资源转换

[scripts/generate-content.mjs](scripts/generate-content.mjs) 相对于各原始源文件解析链接：

- 指向已发布 Markdown 源文件的链接转换为站点路由，包括映射后的根目录与插件文档。
- 共享图片复制到 `public/media/<仓库路径>`，构建后通过 `media/` 访问。Studio 的 logo/icon 也会复制到站点公共目录。
- 指向仓库代码、数据及其他未发布文件的链接转换为 GitHub `blob/main` 或 `tree/main` 地址。
- 转换 Markdown 行内链接与 HTML `<a>`/`<img>` URL，保留围栏代码块中的示例不变。

Markdown 导出使用绝对站点 URL，图片链接也会转换。导出文本包含 UTF-8 BOM，以便未明确设置 charset 的静态主机正确显示中文。

旧路由 `getting-started/introduction` 与 `guides/plugin-management` 已移除，且没有重定向。请改用 `getting-started/overview` 与 `plugins/management`。

## 构建校验

`npm run build` 最后执行 [scripts/verify-build.mjs](scripts/verify-build.mjs)。成功构建会确认：

- 必需的 HTML 页、双语首页、图标、Markdown 导出和 LLM 文本存在且非空。
- 每篇文档仅属于一个导航页签，侧边目录与顶部激活页签正确。
- 中英文文档路由一致，每个导航条目都有两种语言的源文件。
- 编辑链接指向原始源文件，本地 HTML 链接与资源位于部署基础路径内且能找到对应产物。
- Markdown 导出使用绝对 URL（页内锚点除外），文本为有效 UTF-8 并包含预期 BOM。
- 已移除的旧页面没有生成。

这些检查验证生成的本地产物，不验证外部网站、DNS 或线上部署。`format:check` 是独立命令，文档工作流不会自动执行它。

## 部署

[文档工作流](../.github/workflows/docs.yml) 使用 Node.js 22 安装依赖、构建站点，并将 `github-pages/dist/` 上传为 Pages 产物。

- 面向 `main` 的 Pull Request 仅构建与校验，不部署。
- 命中路径条件的 `main` 推送会构建并部署；在 `main` 上手动运行工作流也可部署。
- 监听路径包括 `docs/`、`github-pages/`、根目录 README/贡献指南、两个研究插件目录、Studio logo/icon SVG 和工作流本身。

首次部署前，在仓库的 Pages 设置中选择 **GitHub Actions** 作为发布来源。部署使用 `github-pages` 环境，以及 `pages: write` 和 `id-token: write` 权限。

### 基础路径与自定义域名

| 变量            | 默认值                         | 含义                                               |
| --------------- | ------------------------------ | -------------------------------------------------- |
| `DOCS_BASE`     | `/AxonX/`                      | 站点挂载路径，需包含开头和结尾的斜杠。             |
| `DOCS_SITE_URL` | `https://flowllm-ai.github.io` | Markdown 与 LLM 导出使用的站点源，不包含挂载路径。 |

使用自定义域名并托管在根路径时：

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run build
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run preview
```

在 CI 中配置相同变量，并在 GitHub Pages 设置中配置自定义域名与 DNS。当前工作流显式设置 `DOCS_BASE: /AxonX/`，使用其他挂载路径时需同步修改。开发、构建和预览的基础路径应保持一致。部署生成后的 `dist/` 内容。

## 代码结构

| 路径                                | 职责                                                                 |
| ----------------------------------- | -------------------------------------------------------------------- |
| `scripts/generate-content.mjs`      | 复制正文与主题、映射路由和链接、复制共享资源、生成首页及源文件映射。 |
| `scripts/verify-build.mjs`          | 校验页面、导航、双语路径、链接/资源、编辑链接与导出。                |
| `../docs/.vitepress/config.mts`     | VitePress 配置、语言、搜索、输出路径、原始文件编辑链接与文本导出。   |
| `../docs/.vitepress/navigation.mjs` | 顶部页签与文档归属。                                                 |
| `../docs/.vitepress/links.mjs`      | 围栏代码块之外的链接转换。                                           |
| `../docs/.vitepress/theme/`         | 首页、文档工具、偏好控件与样式。                                     |
| `.generated/site/`                  | VitePress 生成输入，包含 `.source-map.json`。                        |
| `dist/`                             | 可部署的静态 HTML、资源、Markdown 和 LLM 文本。                      |
| `../.github/workflows/docs.yml`     | 文档 CI 与 Pages 部署。                                              |

依赖在 `package.json` 中声明，并通过 `package-lock.json` 锁定。VitePress 固定为 `1.6.4`，Vite override 使用 `^6.4.3` 版本范围。

## 常见问题

| 现象                       | 检查项                                                                |
| -------------------------- | --------------------------------------------------------------------- |
| 开发时看不到修改           | 重启 `npm run dev` 以重新生成原始内容；不要修改 `.generated/`。       |
| 源文件缺失或导航校验失败   | 补齐双语文件，仅注册一次路由，导入页面需检查源文件映射。              |
| 图片或本地链接缺失         | 从原始源文件位置解析路径，确认目标存在于仓库。                        |
| 部署后资源或链接失效       | 将 `DOCS_BASE` 与实际挂载路径保持一致并重新构建。                     |
| 导出链接指向错误域名       | 将 `DOCS_SITE_URL` 设为站点源，`DOCS_BASE` 设为挂载路径，再重新构建。 |
| 页面自动切换到其他语言     | 检查导航菜单中保存的语言偏好。                                        |
| CI 构建成功但 Pages 未部署 | 检查分支与事件、Pages 发布来源、部署环境和工作流权限。                |

内容维护参见[文档索引](../docs/README.md)与[贡献指南](../CONTRIBUTING_ZH.md)。AxonX 采用 [Apache License 2.0](../LICENSE)。
