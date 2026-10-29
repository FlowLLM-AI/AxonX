# 运行与部署

分别管理服务、执行目标和持久研究记录。先通过[快速开始](../getting-started/quickstart.md)验证本机连接，再选择需要的操作。

## 选择操作

| 目标                                  | 指南                                            |
| ------------------------------------- | ----------------------------------------------- |
| 执行、等待、跟踪日志、停止或删除 Task | [任务管理](task-management.md)                  |
| 将已安装 Task 组合成同步流程          | [复合 Task](composite-tasks.md)                 |
| 浏览和检查工作区产物                  | [工作区文件](../concepts/workspace.md#浏览目录) |
| 复制已结束 Task 的快照                | [任务同步](task-sync.md)                        |
| 配置服务访问与令牌                    | [鉴权](authentication.md)                       |
| 托管服务，按需启用 Studio             | [部署](deployment.md)                           |
| CLI 直连或通过 Studio 转发            | [远程机器](deployment.md#远程接入)              |
| 转发配置的 HTTP 请求                  | [HTTP 代理](http-proxy.md)                      |
| 定时执行本地 Task 命令                | [调度](scheduling.md)                           |
| 通过钉钉发送任务通知                  | [通知](../research/notifications.md)            |
| 定位故障、备份与恢复记录              | [排障与恢复](operations.md)                     |

## 明确执行环境

每个执行目标有自己的 Python 环境、插件、数据和工作区。CLI 直连使用目标服务令牌；Studio 使用本机令牌，通过同源后端转发到配置的目标。执行、等待、日志与产物查询应使用同一执行目标。

任务同步复制终态展示快照，也可显式启用父子任务组的实时快照；副本不能作为研究输入。原始行情、插件依赖、模型凭据与 Agent 会话环境需要单独准备。存储边界见[工作区概念](../concepts/workspace.md)，连接优先级见[客户端配置](../reference/client-configuration.md)。

## 维护服务时保留证据

实验使用不同 Task 身份。同名重跑会替换已结束目录，删除会移除记录与产物。显式停止 Task 或取消服务拥有的命令会结束执行，不提供续跑能力。Daemon 拥有的定时命令在服务重启期间继续运行。清理或恢复前先阅读[任务生命周期](../concepts/jobs-and-tasks.md)。
