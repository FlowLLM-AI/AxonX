# 快速开始

使用 Python 3.12+ 安装 AxonX：

```bash
pip install 'axonx[studio]'
axonx exec --task demo --task-name quickstart --x 2 --y 3
```

内置 Demo 不需要行情或模型凭据。命令无需常驻服务即可同步执行，输出结果，并在成功时返回退出码 0。Task ID 为 `base#demo#quickstart`；默认配置下 metadata 位于 `.axonx/base/base#demo#quickstart/metadata.json`。需要保留另一轮实验时使用新名称。

## 启动观察服务

使用与执行进程相同的工作目录、workspace 和日志配置：

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-local-service-token'
axonx start --service.host 127.0.0.1
```

保留该终端，在使用相同环境和 token 的另一终端查询：

```bash
axonx version
axonx status --task-id 'base#demo#quickstart' --detail full
axonx read_task_log --task-id 'base#demo#quickstart'
```

服务默认地址为 `http://127.0.0.1:1024`。Studio 展示已有 Task 记录与只读任务定义，状态来自 Task 自行写入的 metadata。独立本地 exec 不依赖服务可用性，服务不修复中断记录，也不控制这些进程。

## 研究插件

在执行环境安装所需插件、准备数据并检查输入 Schema，再通过 `axonx exec --task <注册名>` 运行。保留参数、数据窗口、Task/Run ID、成本与产物引用。Task 成功不等于研究效果提升。

[Task 执行与观察](../guides/task-management.md) · [插件管理](../plugins/management.md) · [研究流程](../research/workflow.md)
