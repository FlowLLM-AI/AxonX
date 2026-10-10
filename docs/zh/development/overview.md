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
