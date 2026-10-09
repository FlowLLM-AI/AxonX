# Alpha158 Factor

[English](README.md) · [简体中文](README_ZH.md)

`a158_factor` 继承 `a158`，保留 158 个基础特征，增加现有的 26 个因子（184 个特征）。ETL、训练、预测、因子分析和普通回测均复用基线流程；训练默认使用市场、流动性与交互组，模型共 179 个特征；`context_groups` 可选择其他组。

## 因子与时点

市场、流动性、相对表现、交互四组因子由 [cross_section.py](axonx_alpha158_factor/internal/cross_section.py) 定义。金额分组使用截至 T−1 的历史；当日环境信息在收盘后可用。相邻交易日复权收益遇到行情缺失时保持缺失；因子计算不使用未来标签。ETL 保存因子组、时点协议和每日环境诊断。

## 安装与执行

```bash
axonx plugin install plugins/a158 --target http://research.example:1024
axonx plugin install plugins/a158_factor --target http://research.example:1024
axonx submit --task a158f_etl --start-date 20150101 --end-date 20261008 --target http://research.example:1024
axonx submit --task a158f_train --source-tasks '<etl_task_id>' --train-start 20150101 --train-end 20230101 --context-groups market,liquidity,interaction --target http://research.example:1024
axonx submit --task a158f_predict --source-tasks '<train_task_id>' --pred-start 20230101 --target http://research.example:1024
axonx submit --task a158f_backtest --source-tasks '<predict_task_id>' --top-ns '[5,10,20,30]' --as-of-date 20261008 --target http://research.example:1024
```

提交返回实际 Task ID 和 Run ID；按 [开发指南](../../docs/zh/dev_guide.md) 等待 `succeeded` 后再提交下游。`a158f_factor` 是可选的因子分析任务。`context_groups` 默认 `market,liquidity,interaction`，可选子组或 `none`。

## 三层实验

训练 2015–2022，20230101 起至共同数据截止日整体预测、回测。比较仅展示 Top5/10/20/30；每次买卖各收 0.2%。[三层记录](../a158/THREE_LAYER_EXPERIMENTS_ZH.md)保存任务、配置、输入摘要和结果。第二层使用普通回测；第三层 [a158_strategy](../a158_strategy/README_ZH.md) 复用本层预测，只改变持仓决策。

此前采用不同实验窗口的材料保留为历史证据：[历史结果](EXPERIMENT_RESULTS.md) · [历史指标](experiments/README.md)。这些数据不用于本次三层比较。

## 与原增强插件的兼容性

当前源码以 `plugins/a158_factor` 替代 `plugins/a158_enhanced`，发行包、Python 包和插件入口分别改为 `axonx-alpha158-factor`、`axonx_alpha158_factor` 和 `alpha158_factor`；新任务使用 `a158f_` 前缀，原前缀为 `a158e_`。训练默认组改为 `market,liquidity,interaction`。安装新包并重启服务后再提交新任务。既有任务 ID、元数据和产物不会改写。重跑旧 `a158e_` 任务时，应保留或重新安装原增强插件版本；因子插件不注册旧任务名。上述历史报告描述原增强插件版本。
