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

另开终端启动 Python 服务，代理与构建设置见 [Studio 开发](docs/zh/development/studio.md)。

## 选择修改位置

| 位置                          | 职责                                            |
| ----------------------------- | ----------------------------------------------- |
| `axonx/task/`                 | 类型模型、开发基类、同步运行时、存储与内置 Task |
| `axonx/plugin/`               | 插件发现、wheel 校验与安装                      |
| `axonx/app/`、`axonx/client/` | 应用能力、Job、传输和客户端连接                 |
| `axonx/cli/`、`axonx/daemon/` | 命令路由、服务监督与定时进程归属                |
| `plugins/`                    | 研究算法、manifest 与插件测试                   |
| `axonx_studio/`               | 界面、表单、API 客户端与研究视图                |
| `docs/`、`github-pages/`      | 双语指南、图片、导航与站点工具                  |

算法放在 Task/插件中。Task 执行不依赖 App、Plugin 或 CLI，由启动层装配目录并注入宿主能力。从所属模块导入，数据契约不执行运行时操作，资源须明确清理。详见[架构](docs/zh/concepts/architecture.md)、[框架扩展](docs/zh/development/framework-extensions.md)和[依赖图](module-dependencies.md)。

## 开发插件

仅安装本次所需层及其上游依赖，顺序如下：

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

研究插件尚未发布到 PyPI。源码变化后重启常驻服务，依赖或入口点变化后重新安装。远程部署需要构建、上传、目标机安装、暂存清理和重启，见[插件管理](docs/zh/plugins/management.md)。

插件包含包元数据、`axonx.plugins` 入口、`plugin.yaml`、类型化 Task、测试和中英文 README。运行时资源加入 `tool.setuptools.package-data`，打包 CI 会比较 wheel/sdist 与源码内容。实现遵循 [Task 开发](docs/zh/dev_guide.md)与[产物契约](docs/zh/reference/research-artifacts.md)。

Agent 编写的代码遵循相同检查。主张改进时保留源码/插件版本、数据快照、窗口、参数、成本、Task ID 和 `started_at`，提供脱敏复现依据，并遵循[实验设计](docs/zh/research/experiments.md)。

## 验证改动

先运行受影响检查，再运行相关测试集。在 PR 中记录命令、结果和未运行的检查。

| 范围            | 检查                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------- |
| 框架            | `python -m pytest tests`                                                                    |
| 插件            | 对应测试目录，例如 `python -m pytest plugins/qlib_factor/tests`                             |
| Studio          | 在 `axonx_studio/` 执行 `npm test`、`npm run lint`、`npm run format:check`、`npm run build` |
| Python 传输契约 | 在 `axonx_studio/` 执行 `npm run contracts:generate` 和 `npm run contracts:check`           |
| 文档示例        | `python -m pytest tests/unit/test_documentation_contracts.py`                               |

裸命令 `pytest` 还会收集插件测试，需准备研究依赖。默认排除集成测试；运行 `pytest -m integration` 前，准备所需服务和凭据并检查外部影响。

测试使用临时工作区，不提交凭据、私有数据、`.axonx/`、日志或研究生成产物。界面检查覆盖中英文、空数据和请求失败。将实际文件路径传入 `pre-commit run --files <changed-files>`，检查自动修复结果。Hooks 使用 Ruff 整理导入、Black 格式化，并执行其他 lint 检查。

## 更新文档

修改 `docs/en/`、`docs/zh/` 中的规范文档，或被站点引用的根目录/插件 README 与贡献指南。保持双语对应，共享素材位于 `docs/figures/`，导航位于 `docs/.vitepress/navigation.mjs`，生成站点文件由构建重建。

内置 Agent 指南资源链接到 `docs/{en,zh}/dev_guide.md`；可分发 [AxonX Skill](skills/axonx/SKILL.md) 的行为说明应与英文指南一致。核验命令，API 变化时同步更新契约示例。

从仓库根目录准备两组前端依赖并验证站点：

```bash
npm --prefix axonx_studio ci
npm --prefix github-pages ci
npm --prefix github-pages test
npm --prefix github-pages run build
```

构建检查双语页面、链接、资源、锚点和 Markdown 导出，详见[站点开发](github-pages/README_ZH.md)。

## 提交 Pull Request

说明问题、改动后的行为、兼容性影响与验证结果。可见界面改动附截图，注明文档更新情况，推荐 Conventional Commits 标题。贡献遵循 [Apache License 2.0](LICENSE)。

## 发布

主包与 Studio 独立发布，发布前更新版本并通过 CI：

- **AxonX：** 更新 `axonx/_version.py`，推送 `v<version>` 并发布对应 GitHub Release；也可手动运行 [Release / AxonX Python package](.github/workflows/release-python.yml)，输入不带 `v` 的版本号，从该标签构建。
- **Studio：** 同步 `axonx_studio/pyproject.toml`、`package.json` 和 `package-lock.json`，在 `main` 运行 [Release / AxonX Studio](.github/workflows/release-axonx-studio.yml)。`both` 先发 PyPI 再发 npm，`pypi`/`npm` 可单独选择；稳定版 npm 标签为 `latest`，预发布版为 `next`。

配置对应的 Trusted Publisher（`pypi`/`npm` 环境）。已有版本会发布失败，标签不可移动。PyPI 成功而 npm 失败时，在原 workflow 重跑失败 job 以复用产物。主包发布不包含研究插件。
