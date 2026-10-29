# 常见问题

## Studio 打开但数据不加载

静态 UI 可访问不代表服务/API 可用。检查所选机器、token、/health 和公开 Job 目录。服务没有 token 时会隐藏认证能力。

## Exec 输出结果后，任务记录在哪里？

Exec 等待完成并输出业务结果。metadata 位于工作区/type/task_id/metadata.json，也可用完整 status 查询。保留 task_id、started_at、target。连接错误本身不能证明远程命令是否已启动。

## 如何区分同名重跑？

Task ID 标识当前目录，started_at 每次执行改变。wait_task 捕获该值，等待期间重跑会报错。保留独立实验应使用不同名称。

## 声明上游会执行整条链吗？

不会。upstream_task_ids 声明输入依赖，各阶段需显式执行、确认成功并传实际 ID。父子调用属于另一种关系。

## 插件已安装，为何 Studio 不显示？

确认目标解释器和 plugin list。远程原生命令不上传本地源码。安装后重启常驻服务以刷新启动目录和缓存 Schema，新 exec 进程会重新发现已安装元数据。遵循[多步部署流程](plugins/management.md)。

## 停止 Agent 为何研究还在运行？

Agent 轮次与独立 Task 所有权不同。cancel_agent_turn 中断模型会话，CLI kill 停止经验证的 Task 进程，子任务共享根进程。默认远程 cli Job 在客户端断连后继续执行。停止 Task 使用 CLI kill；服务关闭也会终止其手动命令进程组。

## 如何删除 Task？

停止写入者，核对状态/进程身份后，用 delete_entries 删除工作区相对目录。操作也删除持久数据，不保护活动 Task 进程。删除文件不能代替停止执行。

## running 记录为何失效？

观察只读。启动或显式 kill 可修正确认已退出的本机进程；异机或无法访问的进程保持未验证。使用源服务、execution_target 和工作区。

## 预览或副本不完整怎么办？

检查响应截断、采样和省略文件信息。展示副本是观察证据，不是可执行备份。行情缺失可能让回测保持临时结果，即使 Task 执行成功。

[快速开始](getting-started/quickstart.md) · [运维](guides/operations.md) · [Task 契约](reference/task-contracts.md)
