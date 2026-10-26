# Qlib Strategy

[English](README.md) · [简体中文](README_ZH.md)

`qlib_strategy` 继承 `qlib_factor` 和 `qlib_a158`，在同一预测上研究持仓策略。框架统一处理报价、涨跌停、估值、现金、分侧费用、订单、持仓和成交。

## 排名保留策略

- 仍在当日可选 TopN 的持仓继续保留。
- 至少持有 `minimum_holding_days` 个市场日后，优先退出排名最差且已离开缓冲排名的股票。
- 每侧每天最多成交 `max(1,floor(N × replacement_fraction))` 只，首次建仓豁免。
- 无法退出的持仓继续占用资金；买入失败不补位，先卖后买。新仓最多分配 1/N 权益，保留仓位不再平衡。

默认 `minimum_holding_days=10`、`replacement_fraction=0.2`、`rank_buffer=1`。Top5/10/20/30 的每日数量上限为 1/2/4/6 只；它不是资金换手上限。不提供固定到期参数，`planned_exit_date` 为空。

## 安装与执行

研究插件尚未发布到 PyPI。先安装 AxonX 主包并克隆仓库，以下命令从仓库根目录执行。本机 Agent 开发按依赖顺序安装到执行服务的 Python 环境：

```bash
axonx plugin install -e plugins/qlib_a158
axonx plugin install -e plugins/qlib_factor
axonx plugin install -e plugins/qlib_strategy
```

修改 Python 源码后重启常驻服务；依赖或入口点等安装元数据变化后重新安装。固定版本实验去掉 `-e`。远程部署使用普通安装，在同一目标服务按顺序安装上游插件；先配置 `AXONX_TARGET_TOKEN`，并替换以下示例地址：

```bash
# 先构建 wheel 并 POST /upload，再使用返回的绝对路径 location。
axonx plugin install '<uploaded answer.location>' --target http://research.example:1024
# 先构建 wheel 并 POST /upload，再使用返回的绝对路径 location。
axonx plugin install '<uploaded answer.location>' --target http://research.example:1024
# 先构建 wheel 并 POST /upload，再使用返回的绝对路径 location。
axonx plugin install '<uploaded answer.location>' --target http://research.example:1024
axonx exec --task qlib_strategy_backtest --source-tasks '<predict_task_id>' \
  --top-ns '[20,30]' --as-of-date 20261008 \
  --minimum-holding-days 3 --replacement-fraction 0.2 --rank-buffer 1 \
  --buy-cost-rate 0.0005 --sell-cost-rate 0.0015 --target http://research.example:1024
```

可复用成功的基础或增强预测。提交后保存 Task ID 和开始时间，等待成功再读取结果。上游 `qlib_strategy_etl`、`qlib_strategy_analysis`、`qlib_strategy_train`、`qlib_strategy_predict` 注册因子层实现；策略比较直接复用已有预测。安装只修改选定 Python 环境，不刷新服务已加载对象，也不追踪待重启状态。需要重新加载 schema 或贡献时重启常驻服务。新的 CLI 进程加载已安装环境；记录 Task ID 和开始时间，安装或核验失败时停止并报告。

## 实验记录

实验设置、完整结果与产物来源统一见[研究实验指南](../../docs/zh/research/alpha158-case.md)。三组配置已在 45 机器使用买入 0.05%、卖出 0.15% 的费用重新运行。

一次回测 Task 同时发布**全市场**（`all`）与**沪深300**（`hs300`）两个独立报告。Studio 通过下拉框切换股池，策略比较两侧可独立选择。信号时点 `index_weight_hs300 > 0` 定义沪深300成分。新输出使用 `default_universe`、`universes` 和统一产物表，旧回测需重新生成。
