# 常见问题

遇到问题时先区分服务连接、Job 调用与后台 Task 执行。HTTP 请求成功并不意味着后台计算已成功；完整排查流程见 [故障排查](guides/operations.md)。

## Studio 能打开，为什么列表加载失败？

前端静态页面可独立加载，API 仍需要后端在线。检查 `/health`、开发代理地址与服务端日志。使用 Vite 时，修改 `AXONX_DEV_SERVER` 后需要重启。详见 [Studio 入门](getting-started/studio.md)。

## 为什么 /health 或 /jobs 返回 401？

配置服务 token 后，这些协议入口也需要 Bearer token。在 Studio 设置中填写本机服务 token；CLI 使用对应客户端配置。不要把远程机器 token 当成本机服务 token。详见 [客户端配置](reference/client-configuration.md)。

## 为什么能看到目录，却找不到某个 Job？

公开清单来自配置的 Job，而不是所有 Python 方法。需要鉴权的 Job 在未配置服务 token 时可能被过滤；可选组件没有启用时相应功能也可能不可用。以 `/jobs` 和 [配置参考](reference/configuration.md) 为准。

## submit 返回后为什么没有结果？

`submit` 返回 `task_id`、`run_id`、`task`，表示提交已受理。随后调用 `wait_task`、`status` 或查看运行中心。等待时绑定本次 run_id，避免固定名称重跑后读取另一次执行。见 [提交与观察](guides/task-management.md)。

## Task ID 和 run_id 有什么区别？

Task ID 标识工作区内的任务目录；run_id 标识一次执行。同名终态任务再次执行时目录会被替换，因此该目录不是不可变历史档案。详见 [Task 概念](concepts/task-lifecycle.md)。

## 填写 source_tasks 会自动执行上游吗？

不会。它记录来源关系，供上下文与关系图使用。上游任务仍需先执行并产出下游需要的文件。填写多个 Task ID 时用英文逗号，见 [任务关系图](concepts/task-lineage.md)。

## 为什么没有 Alpha158 的训练或回测任务？

它们由研究插件提供，不是安装核心包就必然存在。先检查已安装插件与任务定义，再按 [研究工作流](research/workflow.md) 准备数据。枚举中的类型不代表当前已有具体实现。

## 本地 Python 修改后为什么 worker 没生效？

检查插件的安装方式与所在 Python 环境。开发时使用可编辑安装；长驻服务需要按变更重启以刷新注册状态。后台 worker 是独立进程。见 [插件指南](plugins/management.md)。

## 为什么回测收益和曲线解读不同？

先核对使用的是净收益还是毛收益、交易成本和共同有效交易日。插件的未平仓持仓、信号目标与实际持仓也有不同口径。见 [回测](research/backtest.md) 与 [策略对比](research/strategy-comparison.md)。

## 文件预览报错或不显示完整内容怎么办？

确认使用工作区相对路径，并检查文件是否存在、格式和预览行数限制。预览是有界读取，不等于完整下载。完整产物需在执行机器工作区取得；表格可按支持的分页参数继续预览。见 [工作区指南](guides/workspace-files.md)。

## 远程执行为什么报连接或权限错误？

通过 Studio 或 HTTP 外层 target 转发时，检查目标是否在服务端 targets 配置中；CLI 的 --target 直接连接不要求这个配置。再检查远程服务是否可达、目标 token 是否匹配。Studio 通过本机后端转发，不会从页面直接管理所有远程凭据。见 [机器指南](guides/remote-machines.md)。

## 为什么同步任务后仍缺少原始数据或 Agent 会话？

同步组件是可选的，任务同步聚焦终态任务目录，不负责复制原始数据、插件环境或 Agent 工作区。目标环境仍需单独准备，见 [同步指南](guides/task-sync.md)。

## Agent 页面为什么不能对话？

检查 Agent 组件、SDK、模型环境与可用工具。Agent 会话不等于 Task；请求结束也不一定表示它触发的后台 Task 完成。见 [Agent 配置](agent/configuration.md) 与 [使用指南](agent/usage.md)。

## 取消或删除有什么区别？

取消用于停止正在执行的任务，删除清理任务记录和产物。执行前确认 task_id 并核对当前 run_id；取消接口必须同时指定 task_id 和 run_id，过期请求不会取消新一轮运行。不要通过删除目录代替运行时取消。见 [提交与观察](guides/task-management.md)。

## 下一步

- 从零验证环境：[快速开始](getting-started/quickstart.md)
- 查完整字段：[任务协议](reference/task-contracts.md)
- 查 API 错误：[接口概览](api/overview.md)
- 参与开发：[开发指南](dev_guide.md)
