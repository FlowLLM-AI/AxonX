# 运行与部署

分别管理服务、执行目标和持久研究记录。先通过[快速开始](../getting-started/quickstart.md)验证本机连接，再选择需要的操作。

## 选择操作

| 目标                                  | 指南                                 |
| ------------------------------------- | ------------------------------------ |
| 提交、等待、跟踪日志、取消或删除 Task | [任务管理](task-management.md)       |
| 将已安装 Task 组合成同步流程          | [复合 Task](composite-tasks.md)      |
| 浏览和检查工作区产物                  | [工作区文件](workspace-files.md)     |
| 复制已结束 Task 的快照                | [任务同步](task-sync.md)             |
| 配置服务访问与令牌                    | [鉴权](authentication.md)            |
| 托管服务，按需启用 Studio             | [部署](deployment.md)                |
| CLI 直连或通过 Studio 转发            | [远程机器](remote-machines.md)       |
| 转发配置的 HTTP 请求                  | [HTTP 代理](http-proxy.md)           |
| 定时执行 Job                          | [调度](scheduling.md)                |
| 通过钉钉发送任务通知                  | [通知](../research/notifications.md) |
| 定位故障、备份与恢复记录              | [排障与恢复](operations.md)          |

## 明确执行环境

远程服务拥有自己的插件、数据、工作进程与工作区。CLI 直连使用目标服务令牌；Studio 使用本机令牌，通过同源后端转发到配置的目标。提交、等待、日志与产物查询应使用同一执行目标。

任务同步复制已结束的 Task 目录。原始行情、插件依赖、模型凭据与 Agent 会话环境需要单独准备。存储边界见[工作区概念](../concepts/workspace.md)，连接优先级见[客户端配置](../reference/client-configuration.md)。

## 维护服务时保留证据

实验使用不同 Task 身份。同名重跑会替换已结束目录，删除会移除记录与产物。取消和服务关闭会影响工作进程，但不提供执行续跑能力。清理或恢复前先阅读[任务生命周期](../concepts/task-lifecycle.md)。
