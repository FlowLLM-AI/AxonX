# 参与 AxonX 贡献

[English](CONTRIBUTING.md) · 简体中文

欢迎修复问题、开发研究插件、补充实验证据和文档。先搜索[已有 Issue](https://github.com/FlowLLM-AI/AxonX/issues)，提供复现步骤、预期/实际行为、版本与脱敏日志。大规模公开契约变更先讨论设计，每个 PR 聚焦一个问题。

## 开发环境

macOS 或 Linux 使用 Python 3.12+，从源码仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

Studio 使用 Node.js **22.13+（22.x）、24.x 或 26+**：

```bash
cd axonx_studio
npm ci
npm run dev
```

另开终端，从仓库根目录启动 Python 服务：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

默认端口为 `1024`，运行数据位于 `.axonx/`，服务/CLI 日志位于 `logs/`。可选凭据与内置配置变量见 [example.env](example.env)。CLI 启动时从当前目录或最多五级父目录加载最近的 `.env`，保留已有环境变量。代理与构建设置见 [Studio 开发](docs/zh/development/studio.md)。

YAML 继承与安装配置见[服务端配置](docs/zh/reference/configuration.md)，执行选项见 [CLI 参考](docs/zh/reference/cli.md)。自定义配置只有显式声明 `extends: default` 才继承默认值。凭据和运行产物不得提交。

## 选择修改位置

| 位置                          | 职责                                            |
| ----------------------------- | ----------------------------------------------- |
| `axonx/task/`                 | 类型模型、开发基类、同步运行时、存储与内置 Task |
| `axonx/plugin/`               | 插件发现、wheel 校验与安装                      |
| `axonx/utils/`                | 共享环境、日志、值转换与异步清理                |
| `axonx/app/`、`axonx/client/` | 应用能力、Job、传输和客户端连接                 |
| `axonx/cli/`、`axonx/daemon/` | 命令路由、服务监督与定时进程归属                |
| `plugins/`                    | 研究算法、manifest 与插件测试                   |
| `axonx_studio/`               | 界面、表单、API 客户端与研究视图                |
| `docs/`、`github-pages/`      | 双语指南、图片、导航与站点工具                  |

算法放在 Task/插件中。Task 执行不依赖 App、Plugin 或 CLI，由启动层装配目录并注入宿主能力。`app/core/composition.py` 选择具体 Provider 并编排受管生命周期，Step 通过组件基类契约适配 Job。HTTP/MCP 客户端保持独立于 App。从所属模块导入，数据契约不执行运行时操作，资源须明确清理。详见[架构](docs/zh/concepts/architecture.md)、[框架扩展](docs/zh/development/framework-extensions.md)和[依赖图](module-dependencies.md)。

## 开发插件

研究算法放在插件中。Task 开发遵循[开发与运行指南](docs/zh/dev_guide.md)，安装和远程部署见[插件管理](docs/zh/plugins/management.md)，Studio 接入见[产物契约](docs/zh/reference/research-artifacts.md)。先从源码安装 `qlib_a158`；`qlib_factor` 和 `qlib_strategy` 分别独立扩展它。

Agent 编写的代码遵循相同检查。改进结论需保留代码/数据版本、窗口、参数、成本、Task ID 和 `started_at`，并遵循[实验设计](docs/zh/research/experiments.md)。

## 验证改动

先运行受影响检查，再运行相关测试集。在 PR 中记录命令、结果和未运行的检查。

| 范围            | 检查                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------- |
| 框架            | `python -m pytest tests`                                                                    |
| 插件            | 对应测试目录，例如 `python -m pytest plugins/qlib_factor/tests`                             |
| Studio          | 在 `axonx_studio/` 执行 `npm test`、`npm run lint`、`npm run format:check`、`npm run build` |
| Python 传输契约 | 在 `axonx_studio/` 执行 `npm run contracts:generate` 和 `npm run contracts:check`           |
| 文档示例        | `python -m pytest tests/unit/test_documentation_contracts.py`                               |

另用 `python -m scripts.sync_agent_guides --check` 检查 Agent 资源；架构变更运行 `python -m pytest tests/unit/test_module_boundaries.py`。

裸命令 `pytest` 还会收集插件测试，需准备研究依赖。默认不执行集成测试；运行 `python -m pytest tests/integration -m integration` 前，准备所需服务和凭据并检查外部影响。

契约生成同时更新 `axonx_studio/src/shared/api/contracts.ts` 和 `axonx_studio/src/playground/job-contracts.json`。修改 Python 序列化模型、默认 Job 或 `axonx/_version.py` 后重新生成，不手改生成文件。

测试使用临时工作区，不提交凭据、私有数据、`.axonx/`、日志或研究生成产物。界面检查覆盖中英文、空数据和请求失败。将实际文件路径传入 `pre-commit run --files <changed-files>`，检查自动修复结果。Hooks 使用 Ruff 整理导入、Black 格式化，并执行其他 lint 检查。

## 更新文档

修改 `docs/{en,zh}/` 的中英文规范来源，或由站点导入的根目录/插件 README。操作步骤放在指南，字段放在参考，算法放在插件 README，实验证据放在案例；通过链接引用归属文档，避免复制正文。导航位于 `docs/.vitepress/navigation.mjs`，共享图示位于 `docs/figures/`。

Job 入参以 `axonx/app/config/default.yaml` 为准，CLI 语法属于 `axonx/cli/parser.py`，执行属于 `commands.py`/`remote.py`，Task 契约属于 `axonx/task`。同步更新受影响示例和图示，保留历史研究结果及来源。

修改 `docs/{en,zh}/dev_guide.md` 后运行 `python -m scripts.sync_agent_guides` 和 `python -m scripts.sync_agent_guides --check`，生成包内指南与 `skills/axonx/SKILL.md`。这些独立资源有意保留完整指南。

在 `axonx_studio/` 和 `github-pages/` 安装依赖后运行：

```bash
npm --prefix github-pages test
npm --prefix github-pages run build
```

构建验证双语导航、链接、锚点、资源和 Markdown 导出。生成、图示、部署和 Vercel 设置见[站点维护](github-pages/README_ZH.md)。

## 提交 Pull Request

说明问题、改动后的行为、受影响的契约与验证结果。可见界面改动附截图，注明文档更新情况，推荐 Conventional Commits 标题。贡献遵循 [Apache License 2.0](LICENSE)。

## 发布

主包与 Studio 独立发布，发布前更新版本并通过 CI：

- **AxonX：** 更新 `axonx/_version.py`（当前为 `0.3.1`），重新生成 Studio 契约，推送 `v<version>` 并发布对应 GitHub Release；也可手动运行 [Release / AxonX Python package](.github/workflows/release-python.yml)，输入不带 `v` 的版本号，从该标签构建。
- **Studio：** 同步 `axonx_studio/pyproject.toml`、`package.json` 和 `package-lock.json`，在 `main` 运行 [Release / AxonX Studio](.github/workflows/release-axonx-studio.yml)。`both` 先发 PyPI 再发 npm，`pypi`/`npm` 可单独选择；稳定版 npm 标签为 `latest`，预发布版为 `next`。

配置对应的 Trusted Publisher（`pypi`/`npm` 环境）。已有版本会发布失败，标签不可移动。PyPI 成功而 npm 失败时，在原 workflow 重跑失败 job 以复用产物。主包发布不包含研究插件。

两个 PyPI 发布工作流都使用 Twine 内置的 Trusted Publishing 身份认证，并在生成 Sigstore 签名证明之前检查包元数据。如果签名证明生成失败或超过两分钟，工作流会发出警告，然后不带签名证明继续上传。元数据、身份认证、版本重复和上传错误仍会使发布失败。

[AxonX Skill](skills/axonx/SKILL.md) 随同一仓库和 AxonX 版本标签分发。发布前按上文同步 Agent 指南，并执行 `gh skill publish --dry-run`。复用 AxonX Release；[不带 `--dry-run` 的 `gh skill publish`](https://cli.github.com/manual/gh_skill_publish) 会创建 GitHub Release，`v<version>` 发布会触发 PyPI 工作流。
