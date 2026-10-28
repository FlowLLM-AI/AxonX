# 开发与贡献

本栏目介绍 AxonX 框架与 Studio 的开发。研究算法在插件中实现，见量化研究下的[开发与运行指南](../dev_guide.md)；Agent 驱动的插件开发从 [Skill 与研究 Prompt](../agent/research-prompt.md)开始。

## 选择贡献范围

| 目标                            | 指南                                    | 相关契约                                                                         |
| ------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------- |
| 准备源码环境与检查              | [贡献指南](../../../CONTRIBUTING_ZH.md) | 仓库贡献约定                                                                     |
| 扩展 Component、Job 或异步 Step | [框架扩展](framework-extensions.md)     | [架构](../concepts/architecture.md)、[服务端配置](../reference/configuration.md) |
| 开发 Studio 功能与产物视图      | [Studio 开发](studio.md)                | [研究产物契约](../reference/research-artifacts.md)                               |
| 接入服务客户端                  | [Python 参考](../reference/python.md)   | [HTTP API](../api/overview.md)、[事件](../api/events.md)                         |

## 保持职责与资源边界

复用框架扩展点，保留公开 CLI、API、配置、Task 身份、生命周期和持久记录契约。管理异步资源、流与子进程时，明确所有权和清理方式。研究算法、特征与持仓逻辑留在插件中。

在临时工作区执行针对性的检查，再按[贡献指南](../../../CONTRIBUTING_ZH.md)运行受影响测试与格式检查。代码验证与研究改进证据分别报告。

## 维护文档与站点

中英文同步更新。通用步骤放在指南，字段放在[参考手册](../reference/overview.md)，算法放在插件 README，具体实验放在研究案例。[站点维护指南](../../../github-pages/README_ZH.md)说明导航、生成与构建验证。

## 文档所有权与验证

公共 Job 入参以 `axonx/app/config/default.yaml` 为准，原生命令语法属于 `axonx/cli/parser.py`，执行行为属于 `commands.py`/`remote.py`。Task 模型与开发接口位于 `axonx/task`。契约变化时同时更新引用、示例、图示和中英文。

Agent 指南的规范来源是 `docs/en/dev_guide.md` 和 `docs/zh/dev_guide.md`。修改后运行 `python -m scripts.sync_agent_guides`，同步包内 `axonx/app/components/agent/guides/` 资源和可分发 `skills/axonx/SKILL.md`。生成结果使用普通文件，确保 wheel 和不支持符号链接的检出都包含完整正文；使用 `--check` 检查漂移。常驻服务在启动时重新加载指南。

从仓库根目录，在后端开发环境运行 `python -m pytest tests/unit/test_documentation_contracts.py`；安装两套前端依赖后运行 `npm --prefix github-pages test` 和 `npm --prefix github-pages run build`。契约检查验证所有已配置 Job 的请求示例、文档 CLI 入参/导入和可执行 Task 开发/组合示例。站点构建还检查导航、翻译、锚点、资源和导出。历史研究表格和基准图保留记录值及来源。
