# 开发与扩展 AxonX

研究算法放在插件中，执行、记录与接口复用框架扩展点。改动前先选择需要扩展的层。

## 选择扩展路径

| 目标                            | 从哪里开始                              | 查阅契约                                                          |
| ------------------------------- | --------------------------------------- | ----------------------------------------------------------------- |
| 准备源码环境并运行检查          | [贡献指南](../../../CONTRIBUTING_ZH.md) | 仓库贡献约定                                                      |
| 实现研究 Task                   | [开发与运行指南](../dev_guide.md)       | [Task 输入、输出、身份与生命周期](../reference/task-contracts.md) |
| 打包和注册插件                  | [插件管理](../plugins/management.md)    | [插件清单](../reference/plugin-manifest.md)                       |
| 扩展 Component、Job 或异步 Step | [框架扩展](framework-extensions.md)     | [架构](../concepts/architecture.md)                               |
| 开发 Studio 功能与产物视图      | [Studio 开发](studio.md)                | [研究产物](../reference/research-artifacts.md)                    |
| 接入服务客户端                  | [Python 参考](../reference/python.md)   | [HTTP API](../api/overview.md)与[事件](../api/events.md)          |

开发与运行指南也随安装包提供，可由内置 Agent 按需加载。保留规范的 `dev_guide.md` 路径，供外部 Skill 与源码链接引用；专题页面负责深入解释和字段参考。

## 验证研究改动

发现已注册 Task 的 Schema，在临时工作区执行最小流程，检查输出元数据与声明的产物。特征时点、字段或上游要求变化时，复用旧记录前需要检查兼容性。

算法比较见[实验设计](../research/experiments.md)，Agent 驱动开发见[外部 Agent](../agent/external.md)。[Alpha158 Factor 插件](../../../plugins/a158_factor/README_ZH.md)展示独立实现、特征分组开关与独立确认。

## 维护文档

中英文同步更新。算法细节由插件维护，通用工作流放在指南，字段定义放在参考。[站点维护指南](../../../github-pages/README_ZH.md)介绍导航归属、生成与构建检查。
