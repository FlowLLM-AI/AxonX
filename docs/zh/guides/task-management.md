# 任务提交与管理

本页用内置 demo 演示发现定义、提交、等待、查看状态与日志。前提是服务已按[快速开始](../getting-started/quickstart.md)启动，并配置 `AXONX_SERVICE_TOKEN`。demo 无需数据源或模型凭据。

![任务管理流程](../../figures/guides/task-management.svg)

## 发现定义

```bash
axonx list_installed_task_definitions
axonx get_task_definition --task demo
```

定义返回注册名、来源、Task 类型、说明以及 input_schema/output_schema。demo 必需参数为整数 `x`、`y`，可选 `fail` 用于模拟执行失败。Studio 提交页根据同一 Schema 构建表单。

未知参数通常由 Task 的输入模型拒绝。`submit` 的外层 Schema 允许额外业务参数，是为了透传到具体 Task，并不意味着 Task 任意接收字段。

## 提交并保存 handle

```bash
axonx submit --task demo --task-name add-01 --x 1 --y 2
```

保存 `answer.task_id` 和 `answer.run_id`。这里的 Task ID 为 `base#demo#add-01`，run_id 必须使用实际返回值。

希望保留多轮实验时，应每轮使用新名称或省略 `--task-name`。固定名称在终态后重跑会替换旧目录；活跃任务无法被同名覆盖。

在 Studio 中，选择执行机器、打开任务提交页、选择 demo，然后输入 x/y 并提交。打开任务详情确认身份与状态，避免把提交提示当成执行完成提示。

下图为英文界面的任务列表，`docs-demo` 和 `docs-child` 是为文档创建的两个独立 demo 运行，均已进入 Succeeded。截图中的名称与本页 CLI 的 `add-01` 不同，用于展示同一任务管理流程。

![Studio 英文任务列表中的两个成功 demo 运行](../../figures/studio/task-list.png)

## 等待完成

```bash
axonx wait_task --task-id 'base#demo#add-01' \
  --run-id '<实际返回的 run_id>' --client-timeout 600
```

长任务需要调大客户端超时。默认客户端请求超时为 60 秒；客户端超时或关闭浏览器不等于 Task 被取消，可以重新查状态。

成功时 `answer.state` 为 succeeded，`answer.result` 包含 result=3、branch=different、operands 等输出。失败时 JobResponse.success 为 false，应继续读取 error 和日志。

实时观察可使用：

```bash
axonx stream_task --task-id 'base#demo#add-01' \
  --stream true --client-timeout 600
```

事件流适合进度和日志展示，`wait_task` 适合确认指定 run_id 的终态。只订阅流但不检查最终 result，无法可靠判定研究成功。

## 查询状态和日志

```bash
axonx list_task_ids
axonx list_task_statuses
axonx status --task-id 'base#demo#add-01'
axonx read_task_log --task-id 'base#demo#add-01' --offset -1 --limit 65536
```

日志 offset 单位是字节，`-1` 读取尾部，正值从指定字节偏移读取；limit 范围为 1024–262144，默认 65536。后续增量读取应使用响应提供的偏移信息，不按字符数自行计算。

Studio 详情中的 Run details 展示退出码、步骤和输出。下图的 `docs-demo` 使用 x=2、y=3，依次完成 initialize、add_x、add_y、finish 四步，result 为 5。图片只保留执行详情区域，底部 Output JSON 未完整显示；需要完整结果时读取 API 响应或 metadata。

![Studio 英文任务详情中的四个完成步骤及输出片段](../../figures/studio/task-details.png)

日志区域可以进一步核对每一步使用的参数和累计结果。下图可见 total 从 2 变为 5，最终 exit_code=0；截图已移除个人绝对路径，仅保留日志正文。

![Studio 英文任务日志中的 demo 执行过程](../../figures/studio/task-logs.png)

任务进度事件与文本日志属于不同记录。检查错误时先看 status.error，再看日志上下文；输出截断表示读取窗口有限，不代表原日志只有这些内容。

## 查看成功元数据

```bash
axonx preview_file --path 'base/base#demo#add-01/metadata.json'
```

metadata 位于类型目录下，成功输出在 `output_params`，不是顶层 result。demo 是 base 类型，不会出现在 ETL、训练或回测研究结果列表。

研究插件应另外检查 artifacts 指向的文件存在，图表数据与参数一致。状态成功仅说明框架执行完成，并不证明策略或数据质量达到研究要求。

## 失败、取消与重跑

```bash
# 此任务用于观察 failed；运行命令本身返回的是提交 handle
axonx submit --task demo --task-name failure-01 --x 1 --y 2 --fail true
axonx status --task-id 'base#demo#failure-01'

# 对仍在运行的真实研究任务取消
axonx cancel --task-id '<活跃 Task ID>'
```

demo 很快完成，通常不能用它稳定演示取消。取消返回 false 时，应核对任务是否已经结束、是否由当前管理器管理，以及执行机器是否选择正确。

修正参数后可用新名称保留失败记录；复用固定名称会替换旧任务目录。没有通用的自动断点续跑，插件自己实现恢复时应遵循其文档。

## 删除终态任务

```bash
axonx delete_tasks --task-ids '["base#demo#failure-01"]'
```

删除只适用于终态或 metadata-only 记录，活跃任务会被拒绝。删除会移除任务文件，清理前先检查[血缘关系](../concepts/task-lineage.md)，确保上游产物不再被需要。

一般任务清理使用 `delete_tasks`；任意工作区文件删除使用 `delete_entries`，两者的范围与保护不同。

## 常见失败

| 现象 | 检查与处理 |
| --- | --- |
| Job 目录缺少 submit | 配置服务 token 并重启；查看实际 `/jobs` |
| Unknown Task | 在执行机器安装插件，重新查询定义 |
| 同名目录已存在 | 等活跃任务结束，或使用新名称 |
| wait 的运行身份不匹配 | 检查是否同名重跑，使用原始 handle |
| 任务列表有记录，研究页没有 | 检查是否研究类型及成功 metadata |

[Task API](../api/tasks.md) · [生命周期](../concepts/task-lifecycle.md) · [Task 契约](../reference/task-contracts.md)

源码：[任务命令 Step](../../../axonx/steps/task/command.py)、[TaskManager](../../../axonx/components/task_manager/local/manager.py)。
