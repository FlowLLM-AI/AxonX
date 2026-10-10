# AxonX 文档导航

AxonX 是面向 Agent 的量化研究 Harness，为量化代码开发、实验执行和结果分析提供统一工具与运行环境。用户提出研究问题，Agent 实现量化逻辑，Harness 管理执行与证据。

参考研究插件适配 [Microsoft Qlib](https://github.com/microsoft/qlib) 的 Alpha158 基线，扩展可选因子与持仓策略。其他研究方法也可通过插件接入 AxonX。

## 选择你的起点

| 目标            | 从这里开始                                                                           | 完成结果                           |
| --------------- | ------------------------------------------------------------------------------------ | ---------------------------------- |
| 第一次使用      | [快速开始](getting-started/quickstart.md) → [Studio 入门](getting-started/studio.md) | 提交 demo、等待成功并检查记录      |
| 使用 Agent 开发 | [Agent 开发](agent/overview.md) → [Skill 与研究 Prompt](agent/research-prompt.md)    | 准备源码、工具与目标，开始插件开发 |
| 运行研究基线    | [量化研究](research/overview.md) → [Alpha158 流程](research/workflow.md)             | 从数据到训练、预测与回测           |
| 实现研究插件    | [开发与运行指南](dev_guide.md) → [插件管理](plugins/management.md)                   | 实现 Task，安装并发现插件          |
| 评估改动        | [实验设计](research/experiments.md) → [Alpha158 案例](research/alpha158-case.md)     | 比较候选、保留证据、明确限制       |
| 管理执行服务    | [运行与部署](guides/overview.md)                                                     | 跟踪任务，管理文件与远程环境       |
| 查字段与协议    | [参考手册](reference/overview.md)                                                    | 查询接口、配置和扩展契约           |
| 修改 AxonX 本身 | [开发与贡献](development/overview.md)                                                | 扩展框架或 Studio，完成贡献检查    |

项目定位、插件体系与案例摘要见[项目概览](../../README_ZH.md)。内置 demo 无需行情或模型凭据；研究插件需要数据，内置 Agent 需要服务端模型配置，外部 Agent 使用宿主的模型配置。

## 推荐阅读顺序

首次使用先跑通 demo，再阅读 [Job 与 Task](concepts/jobs-and-tasks.md)、[生命周期](concepts/task-lifecycle.md)、[工作区](concepts/workspace.md)和[血缘](concepts/task-lineage.md)。实现原理见[架构](concepts/architecture.md)。

主要研究路径为：**接入 Agent → 提出研究目标 → 开发插件 → 安装到执行服务 → 运行 Task → 检查产物 → 比较与迭代**。Agent 开发介绍宿主、工具和 Prompt；量化研究介绍算法实例、插件开发与评估；开发与贡献介绍框架及 Studio 修改。

各页面只有一个导航归属，相关步骤通过交叉链接连接。操作指南说明步骤，参考手册定义字段与契约，插件 README 维护算法，研究案例保留设定、指标、复现命令和 Task 来源。

## 阅读约定

中英文使用相同页面路径，共享截图和图示。示例地址、凭据和 Task ID 需要替换为实际值；以所连服务发现的 Job 与 Task Schema 为准。

提交成功表示已受理，仍需等待 Task 终态。血缘记录不会自动调度整张 DAG。同名重跑会替换已结束任务目录，比较实验应保留不同身份的记录。

遇到问题先查[常见问题](faq.md)，再按[排障与恢复](guides/operations.md)定位服务、Job 或 Task 层的故障。
