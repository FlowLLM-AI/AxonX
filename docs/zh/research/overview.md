# 量化研究

在插件中实现量化逻辑，通过 Task 执行并保留证据，再用一致的口径评估改动。AxonX 提供统一契约与运行环境，研究算法和数据要求由插件定义。参考工作流适配 [Microsoft Qlib](https://github.com/microsoft/qlib) 的 Alpha158 基线，其他方法也可以通过插件接入。

## 选择研究步骤

| 目标                  | 从这里开始                                                               | 完成结果                                     |
| --------------------- | ------------------------------------------------------------------------ | -------------------------------------------- |
| 让 Agent 实现研究目标 | [Skill 与研究 Prompt](../agent/research-prompt.md)                       | 明确假设、基线、控制条件与工具               |
| 运行 Alpha158 基线    | [Tushare 数据](tushare.md) → [Alpha158 研究流程](workflow.md)            | 成功的 ETL → Train → Predict → Backtest 记录 |
| 开发或优化插件        | [开发与运行指南](../dev_guide.md) → [插件管理](../plugins/management.md) | 实现、注册、安装并发现 Task                  |
| 检查执行产物          | [结果解读](results.md) → [回测口径](backtest.md)                         | 检查特征、模型、预测与组合账本               |
| 评估研究改动          | [策略比较](strategy-comparison.md) → [实验设计](experiments.md)          | 对齐口径、控制变量与独立确认                 |
| 复现已有案例          | [Alpha158 改进实验](alpha158-case.md)                                    | 设定、指标、命令与 Task/Run 来源             |

## 从基线逐层扩展

[Alpha158](../../../plugins/qlib_a158/README_ZH.md)提供 158 个价量特征、LightGBM、因子分析与 TopN 回测。[Qlib Factor](../../../plugins/qlib_factor/README_ZH.md)扩展 ETL 与训练，提供 13 个可选特征；训练默认仍使用 158 个基线特征。[Qlib Strategy](../../../plugins/qlib_strategy/README_ZH.md)复用预测，增加最短持有期、排名保留与换仓数量限制。

参数、算法与产物定义由插件 README 维护。提交前查询所选服务的实际 Task Schema，核对上游兼容性；产物字段见[研究产物契约](../reference/research-artifacts.md)。

## 执行与结论

源码修改、服务安装与 Task 提交分别完成。每次保留代码版本、数据快照、窗口、参数、成本和真实 Task/Run ID。等待上游成功后再提交下游；血缘记录不会自动调度整张 DAG。因子分析从 ETL 独立分支，不是训练的前置条件。

Task 成功说明执行完成。算法改进需要可比设定、候选选择记录与独立确认。[Alpha158 案例](alpha158-case.md)展示三组固定配置的结果，同时保留数据不完整、参数差异和未独立确认的限制。
