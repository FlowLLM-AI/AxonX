# 量化研究

用 AxonX 将研究步骤组织为 Task，明确输入、保留可检查的产物并记录上下游关系。先完成服务连接与 [demo 教程](../getting-started/quickstart.md)。研究算法与数据要求由安装的插件定义。

## 选择下一步

| 目标               | 指南                               | 完成结果                                     |
| ------------------ | ---------------------------------- | -------------------------------------------- |
| 执行 Alpha158 链路 | [研究流程](workflow.md)            | 成功的 ETL → Train → Predict → Backtest 记录 |
| 准备历史行情       | [Tushare 数据](tushare.md)         | 覆盖实验区间的原始分区与基础数据             |
| 检查阶段产物       | [结果解读](results.md)             | 特征、模型、预测与回测证据                   |
| 评估一次改动       | [实验设计](experiments.md)         | 控制变量、消融、锁定方案与独立确认           |
| 解读组合指标       | [回测口径](backtest.md)            | 收益、费用、回撤与执行假设                   |
| 比较两项策略       | [策略比较](strategy-comparison.md) | 共同有效日期上的指标                         |

因子分析是 ETL 的独立分支，不是训练的前置条件。提交返回运行句柄；等待本次执行成功后，再将 Task ID 传给下游。血缘记录依赖关系，不会自动调度整条链路。

## 选择研究插件

[插件管理](../plugins/management.md)介绍执行环境中的安装与发现。[Alpha158](../../../plugins/a158/README_ZH.md)提供基线价量特征、LightGBM 训练与 TopN 回测；[Alpha158 Factor](../../../plugins/a158_factor/README_ZH.md)增加独立注册的 Task 和可配置特征分组。

提交前发现实际安装的 Task Schema。参数、算法与产物定义由插件维护；为 Studio 实现输出时，查阅[研究产物契约](../reference/research-artifacts.md)。

## 阅读 Agent 开发实验案例

[README Benchmark](../../../README_ZH.md#benchmark-agent-开发市场横截面增强特征)在完整的 2022 年后区间比较基础特征、选定环境因子与组合策略。策略层 Top20／Top30 净年化为 27.59%／22.14%。该区间用于选择方案，且市场数据存在缺失，结果仍属探索性、暂定结果。

可复用的方法见[实验设计](experiments.md)，已记录的证据见[三层实验记录](../../../plugins/a158/THREE_LAYER_EXPERIMENTS_ZH.md)。Agent 接入方式见[外部 Agent](../agent/external.md)。
