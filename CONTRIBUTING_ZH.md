# 参与 AxonX 贡献

[English](CONTRIBUTING.md) · 简体中文

欢迎问题反馈、功能建议、文档改进、研究插件和代码贡献。

## 开始之前

搜索[已有 Issues](https://github.com/FlowLLM-AI/AxonX/issues) 和相关代码。反馈问题时，请提供复现步骤、预期与实际行为、环境版本，以及已移除凭据的相关日志。提出功能建议时，请说明研究或开发中遇到的问题和期望行为。

新建 Issue 时，使用问题反馈、功能建议或使用问题表单，其他主题可使用空白 Issue。问题反馈请区分已复现故障、间歇性观察和静态分析推测，注明问题范围及本地或远程 target。分享脱敏片段即可，请勿上传整个 `.axonx/` 工作区。

涉及公开 CLI/API/配置契约、持久化任务记录或任务生命周期的较大改动，建议先通过 Issue 讨论设计。每个 PR 聚焦一个完整问题。

## 选择修改位置

| 位置                                              | 职责                                                      |
| ------------------------------------------------- | --------------------------------------------------------- |
| `axonx/`                                          | Application 组装、Component、Job、CLI、服务与 Task 运行时 |
| `plugins/`                                        | 研究 Task、算法、插件 manifest 与插件测试                 |
| `axonx_studio/`                                   | 浏览器 UI、API 客户端、任务表单与研究图表                 |
| `tests/`                                          | 框架单元测试与集成测试                                    |
| `docs/en/`、`docs/zh/`、`docs/figures/`           | 双语指南与共享截图、示意图                                |
| `docs/.vitepress/navigation.mjs`、`github-pages/` | 文档导航、主题与站点构建工具                              |

实现契约见 [Task 开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide)、[框架扩展](https://flowllm-ai.github.io/AxonX/zh/development/framework-extensions)和[插件协议](https://flowllm-ai.github.io/AxonX/zh/reference/plugin-manifest)。

## 一、贡献 AxonX 框架

适用于 `axonx/` 中的运行时、CLI、HTTP/MCP 服务、通用扩展点，以及配套的 Studio 和框架测试。研究 Task 和算法请按下面的 Plugin 贡献流程开发。

### 开发环境

Fork 仓库并克隆自己的 fork。在仓库根目录使用 Python 3.12+，本地开发环境支持 macOS 和 Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

Studio 使用 Node.js 22.13+（22.x）、24.x 或 26+，运行：

```bash
cd axonx_studio
npm ci
npm run dev
```

按[快速开始](https://flowllm-ai.github.io/AxonX/zh/getting-started/quickstart)另行启动 Python 服务。代理配置见 [Studio 开发](https://flowllm-ai.github.io/AxonX/zh/development/studio)。文档站要求 Node.js 22+。

### 实现改动

复用已有契约和扩展点。研究算法放在 Task/插件中，框架中的异步资源应保持明确的所有权和清理逻辑。主动变更 CLI 参数、API 响应、配置、任务身份或产物格式时，应同步说明。

测试使用临时工作区。不提交 `.env`、token、私有数据、运行时 `.axonx/` 内容、日志和生成产物。截图中不得包含凭据或私有会话内容。

### 验证

按改动范围选择检查，在 PR 中说明命令和结果。框架 Python 改动先运行相关测试，再按需要运行框架测试集：

```bash
pytest tests/unit/<affected_test_file>.py
pytest tests
```

`pytest tests` 和直接运行 `pytest` 都会排除标记为 `integration` 的测试；后者还会收集因子和策略插件测试，需要先安装对应研究依赖。运行 `pytest -m integration` 前，应准备必要凭据与服务，并检查测试对外部系统的影响。无法运行的检查请说明原因。

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
npm ci && npm run build
```

构建会验证渲染页面和 Markdown 导出。根目录及插件 README 和贡献指南由同一构建直接渲染；同步更新中英文，并核查示例命令。

## 二、贡献 Plugin

适用于 `plugins/` 中的研究 Task、因子、模型、策略、回测算法及插件配置。新增研究能力时，优先复用框架的 Task 和扩展点；只有需要通用运行时能力时，再考虑修改 `axonx/`。

### 开发环境

先按框架贡献中的步骤创建 Python 环境、安装主包及开发依赖，再以 editable 模式安装本次开发所需的插件：

```bash
axonx plugin install -e ./plugins/qlib_a158
# 因子和策略层：
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

仓库中的研究插件尚未发布到 PyPI，必须在同一 Python 环境按 Alpha158 → factor → strategy 顺序安装需要的插件及上游依赖。`-e` 仅支持本机源码目录，不能与 `--target` 或 `--output` 同用；远程部署使用普通 `axonx plugin install` 并在同一目标服务遵循上述顺序。修改 Python 源码后重启常驻服务；依赖或入口点等安装元数据变化后重新安装。

默认 pytest 配置包含因子和策略插件测试及三个插件的源码路径。运行这些测试时，通过上述安装准备研究依赖。插件发现和重启行为见[插件指南](https://flowllm-ai.github.io/AxonX/zh/plugins/management)。

### 实现改动

参考现有插件组织代码，并遵循 [Task 开发指南](https://flowllm-ai.github.io/AxonX/zh/dev_guide)和[插件协议](https://flowllm-ai.github.io/AxonX/zh/reference/plugin-manifest)。新增插件应包含包元数据、插件入口与 manifest、Task 实现、示例配置、测试和中英文 README。

保持任务身份、生命周期、配置和产物格式的兼容性；有意变更时，在文档和 PR 中说明。新增运行时资源时更新 `tool.setuptools.package-data`，确保 wheel 和 sdist 包含这些文件。测试使用临时工作区，研究数据、凭据和实验生成产物不提交到仓库。

### 使用 Agent 开发

外部或内置 Agent 可以结合 [AxonX Skill](skills/axonx/SKILL.md) 与研究 Prompt，开发新插件或优化已有插件。
提供源码仓库、文件／命令工具和选定的执行服务；两条接入路径见 [Agent 总览](docs/zh/agent/overview.md)。
区分插件代码改动、安装与实验执行，Agent 编写的代码遵循相同的贡献检查。

以适配后的 Qlib Alpha158 插件为参考实现，独立的因子和策略插件可以复用兼容的上游代码与产物。
主张研究改进时，记录代码版本、数据快照、训练／评估窗口、参数、成本和 Task/Run ID，遵循[实验设计](docs/zh/research/experiments.md)。
原始执行记录保留在研究环境，公开脱敏后的证据与复现说明。

### 验证

从仓库根目录先运行受影响插件的测试，例如：

```bash
pytest plugins/qlib_factor/tests
pytest plugins/qlib_strategy/tests
```

按实际修改选择命令；涉及框架交互时补充相关框架测试。安装相关研究依赖后，按需要运行 `pytest`。外部服务测试遵循上面的集成测试要求，并在 PR 中说明使用的依赖、验证结果与未运行的检查。主包发布不会发布研究插件，插件的打包和发布需单独处理。

## 两类贡献的共同要求

提交前运行 `pre-commit run --files <changed-files>`，将占位符替换为本次修改的文件路径。文档、PR 和发布要求见下文。

## 文档贡献

修改 `docs/` 下的规范指南，或站点引用的根目录/插件 README 与贡献指南，同步更新中英文。保持相同路径，共享素材放在 `docs/figures/`。站点导航定义位于 `docs/.vitepress/navigation.mjs`。

不修改 `github-pages/.generated/` 或 `github-pages/dist/`，它们会重新生成。站点开发与部署见 [github-pages/README.md](github-pages/README.md)。根目录 README 和贡献指南中的说明变化也应保持双语一致。

## 提交 Pull Request

使用清晰的标题，推荐 Conventional Commits，例如 `fix(tasks): preserve run status` 或 `docs: clarify quick start`。说明问题、改动后的行为、兼容性影响和验证结果。可见 UI 改动附上截图，注明跳过的外部服务测试。

PR 模板会提示这些信息。请列出验证命令和结果，解释未运行检查的原因，并说明中英文文档更新情况。不适用的可选章节可以删除。

贡献遵循项目的 [Apache License 2.0](LICENSE)。

## 发布

主包和 Studio 独立发布。发布前提交版本更新并确保相关 CI 通过；集成测试需要模型 API key，仅在本地按需执行。

- **AxonX**：更新 `axonx/_version.py`，创建并推送 `v<version>` 标签。发布该标签的 GitHub Release 会自动上传 `axonx` 到 PyPI；也可手动运行 `Release / AxonX Python package`，输入不带 `v` 的版本号。
- **Studio**：同步 `axonx_studio/pyproject.toml`、`package.json` 和 `package-lock.json` 的版本，推送到 `main`。手动运行 `Release / AxonX Studio` 并选择 `main` 分支，版本自动读取，不需要标签或版本输入。默认 `both` 先发布 PyPI 再发布 npm；`pypi`、`npm` 可独立发布。npm 标签自动选择：稳定版本使用 `latest`，预发布版本使用 `next`。

AxonX 从发布标签构建；Studio 从手动运行时选定的 `main` 提交构建。两者都校验产物版本。Studio 的 Python/npm 包携带同一份静态资源，预发布版本在 Python 产物中按 PEP 440 规范化。主包发布不会上传研究插件。

打包 CI 还会检查研究插件的 wheel 和 sdist 是否包含全部 Python 模块及 `tool.setuptools.package-data` 声明的数据文件，并逐字节比较它们与源码的内容。添加运行时资源时，请更新 package-data 声明；声明的模式必须能匹配到源码文件。

在 PyPI 为 `axonx` 和 `axonx-studio` 分别配置对应工作流的 Trusted Publisher，环境名为 `pypi`。在 npm 为 `@flowllm-ai/axonx-studio` 配置 `release-axonx-studio.yml` 的 Trusted Publisher，环境名为 `npm`。新的 npm 包需先完成首次发布，再配置 Trusted Publishing。

版本已存在时发布失败，不覆盖或静默跳过。双发中 npm 失败后，优先在原 workflow run 中重跑失败 job，复用同一份产物。也可单包发布；通过新运行补发时应保持 Studio 源码不变。AxonX 发布标签不可移动。
