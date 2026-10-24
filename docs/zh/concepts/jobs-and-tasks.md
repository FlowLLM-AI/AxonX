# Jobs 与 Tasks

Job 是服务处理的一次请求。Task 观察类 Job 返回状态快照、日志或事件流。Task 是通过 `axonx exec` 启动的同步研究执行，拥有持久化身份和产物。

Task Runner 负责发布生命周期和清理资源。服务中的 TaskRepository 轮询执行进程写入的 metadata，生成状态摘要和依赖图。服务不再设置 TaskManager，也不返回后台提交句柄。

`exec` 输出 Task 结果并返回退出码；普通 Job 使用 JobResponse。`wait_task` 与 `stream_task` 观察已有执行。Studio 展示 Task 定义和已有记录，不再提供 Task 启动、取消或删除入口。

远程 CLI、通用工作区删除和副本同步仍属于独立能力。远程 exec 仍然同步执行，进程属于远程 CLI 请求；断开请求或关闭服务会终止该命令。这与独立启动的本地 exec 生命周期不同。
