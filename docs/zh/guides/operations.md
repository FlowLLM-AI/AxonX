# 运维与恢复

## 建立基本状态

```bash
axonx version
axonx diagnose
axonx plugin list
axonx list_task_statuses --detail summary
```

一起记录执行机器、工作区、Task ID 和 started_at。本地 plugin list 描述 CLI 解释器，查询服务环境需添加 --target。

## 日志来源

连接、启动、更新问题检查服务/Daemon 日志。Task metadata.log_path 指向执行日志，read_task_log 返回有限字节块。定时 stdout/stderr 还记录在日志目录的 cron/entry-N.log。文件存在不代表业务评价成功。

## 执行失败或断开

分别检查原生命令 exit_code、Task state/error、进程身份和业务输出。断开后重试前确认 Task 是否已启动、started_at 是否改变。手动远程 CLI 请求拥有进程，取消请求或服务关闭可能终止其进程组。

## 失效记录

观察不改写 running 记录。运行时启动和显式 kill 按机器/PID/进程启动时间修正确认已退出的本机执行。无法访问和异机进程保持未验证，需使用源服务及工作区。共享工作区不把执行所有权交给观察服务。

## 备份与恢复

需要时一起备份 Task 目录、persistent/、源码/插件版本、配置、凭据、独立日志和 Agent 状态。复制关联文件前暂停写入。恢复记录不会恢复进程；重装匹配插件、恢复环境配置、启动目标服务，并在新执行前核验数据/模型修订。

展示同步是有大小限制的证据复制，不是完整备份；省略/采样文件和环境需另行保存。索引可由有效 metadata 重建，不要通过删除活动目录修复执行。

[任务管理](task-management.md) · [同步](task-sync.md) · [自更新](self-update.md)
