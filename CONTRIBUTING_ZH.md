# 参与 AxonX 贡献

[English](CONTRIBUTING.md) · 简体中文

欢迎问题反馈、功能建议、文档改进、研究插件和代码贡献。

## 开始之前

搜索[已有 Issues](https://github.com/FlowLLM-AI/AxonX/issues) 和相关代码。反馈问题时，请提供复现步骤、预期与实际行为、环境版本，以及已移除凭据的相关日志。提出功能建议时，请说明研究或开发中遇到的问题和期望行为。

涉及公开 CLI/API/配置契约、持久化任务记录或任务生命周期的较大改动，建议先通过 Issue 讨论设计。每个 PR 聚焦一个完整问题。

## 选择修改位置

| 位置 | 职责 |
| --- | --- |
| `axonx/` | Application 组装、Component、Job、CLI、服务与 Task 运行时 |
| `plugins/` | 研究 Task、算法、插件 manifest 与插件测试 |
| `axonx_studio/` | 浏览器 UI、API 客户端、任务表单与研究图表 |
| `tests/` | 框架单元测试与集成测试 |
| `docs/en/`、`docs/zh/`、`docs/figures/` | 双语指南与共享截图、示意图 |
| `docs/.vitepress/`、`github-pages/` | 文档主题与站点构建工具 |

实现契约见 [Task 开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide)、[框架扩展](https://flowllm-ai.github.io/AxonX/zh/development/framework-extensions)和[插件协议](https://flowllm-ai.github.io/AxonX/zh/reference/plugin-manifest)。

## 开发环境

Fork 仓库并克隆自己的 fork。在仓库根目录使用 Python 3.12+，本地开发环境支持 macOS 和 Linux：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pre-commit install
```

开发研究插件时，以 editable 模式安装对应插件：

```bash
axonx plugin install -e ./plugins/a158
# Or: axonx plugin install -e ./plugins/a158_enhanced
```

默认 pytest 配置包含 enhanced 插件测试及两个插件的源码路径。运行这些测试时，通过上述安装准备研究依赖。插件发现和重启行为见[插件指南](https://flowllm-ai.github.io/AxonX/zh/guides/plugin-management)。

Studio 使用 Node.js 22.13+（22.x）、24.x 或 26+，运行：

```bash
cd axonx_studio
npm ci
npm run dev
```

按[快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart)另行启动 Python 服务。代理配置见 [Studio 开发](https://flowllm-ai.github.io/AxonX/zh/development/studio)。文档站要求 Node.js 22+。

## 实现改动

复用已有契约和扩展点。研究算法放在 Task/插件中，框架中的异步资源应保持明确的所有权和清理逻辑。主动变更 CLI 参数、API 响应、配置、任务身份或产物格式时，应同步说明。

测试使用临时工作区。不提交 `.env`、token、私有数据、运行时 `.axonx/` 内容、日志和生成产物。截图中不得包含凭据或私有会话内容。

## 验证

按改动范围选择检查，在 PR 中说明命令和结果。Python 或插件改动先运行相关测试，再按需要运行非集成测试集：

```bash
pytest tests/unit/<affected_test_file>.py
pytest
pre-commit run --all-files
```

直接运行 `pytest` 会排除标记为 `integration` 的测试。运行 `pytest -m integration` 前，应准备必要凭据与服务，并检查测试对外部系统的影响。无法运行的检查请说明原因。

Studio 改动在 `axonx_studio/` 中运行：

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

检查相关界面的中英文流程，包括空数据与请求失败。

文档或主题改动在 `github-pages/` 中运行：

```bash
npm ci
npm run build
```

构建会验证渲染页面和 Markdown 导出。根 README/贡献指南改动应检查本地链接、文档路由和示例命令；这些文件不在文档站构建的渲染范围内。

## 文档贡献

修改 `docs/` 下的规范源文件，同步更新对应中英文指南。保持相同路径，共享素材放在 `docs/figures/`。站点导航定义位于 `docs/.vitepress/navigation.ts`。

不修改 `github-pages/.generated/` 或 `github-pages/dist/`，它们会重新生成。站点开发与部署见 [github-pages/README.md](github-pages/README.md)。根目录 README 和贡献指南中的说明变化也应保持双语一致。

## 提交 Pull Request

使用清晰的标题，推荐 Conventional Commits，例如 `fix(tasks): preserve run status` 或 `docs: clarify quick start`。说明问题、改动后的行为、兼容性影响和验证结果。可见 UI 改动附上截图，注明跳过的外部服务测试。

贡献遵循项目的 [Apache License 2.0](LICENSE)。
