---
title: 钉钉通知
description: 使用内置 API Task 向配置的钉钉应用机器人群发送文本或 Markdown。
---

# 钉钉通知

`send_dingtalk_task` 是独立的 `api` 类型 Task，向环境配置的所有群发送一次消息。它没有自动绑定研究任务完成事件；需要调用方在研究成功或失败之后显式提交。

## 前置条件

准备可用的钉钉应用机器人凭据和接收群，放入**执行任务机器**的环境中。不要把凭据写进 Task 参数或研究产物。

```bash
export DINGTALK_CLIENT_ID='<应用 client id>'
export DINGTALK_CLIENT_SECRET='<应用 client secret>'
export DINGTALK_CONVERSATIONS='{"research":"<open conversation id>"}'
```

`DINGTALK_CONVERSATIONS` 必须是非空 JSON 对象；key 是非空字符串标签，value 是非空字符串群标识。重复 value 会去重。当前 Task 不接受选择群的参数，提交后发送到所有配置的唯一群。

## 发送 Markdown

![DingTalk notification submission form](../../figures/studio/notification-submit.png)

Studio 中选择 `send_dingtalk_task`，填写 Title、Text 和 Message Type 后再提交。截图为空白表单，不包含接收群或凭据；提交会向执行机器配置的群实际发送消息。

下面是会实际发送外部消息的使用示例，按自己的接收配置执行：

```bash
axonx submit --task send_dingtalk_task \
  --title 'AxonX 研究完成' \
  --text '### 回测已完成\n请在 Studio 查看对应 Task 的净收益、成本和执行协议。' \
  --message-type markdown
```

需要真正换行时，使用 shell 正确构造包含换行的字符串，或者通过 JSON/调用代码传参。普通单引号内的 `\n` 是两个字符，不会自动变成换行：

```bash
message=$(cat <<'MESSAGE'
### AxonX 研究完成
请查看对应 Task 的 metadata 与标准产物。
MESSAGE
)
axonx submit --task send_dingtalk_task \
  --title 'AxonX 研究完成' --text "$message" --message-type markdown
```

文本模式可设 `--message-type text`。`title` 与 `text` 分别至少包含一个字符；`timeout` 默认 10 秒且必须大于零。

## 等待并核对返回

保存提交返回的 TaskHandle，并等待对应 `task_id` 与 `run_id`。成功输出包含：

| 字段                 | 含义                           |
| -------------------- | ------------------------------ |
| `recipients`         | 去重后的接收群数量，至少 1     |
| `process_query_keys` | 钉钉返回的消息处理查询标识列表 |

这些标识说明接口接受并返回引用，不等价于每个群成员已经阅读。普通 AxonX 提交成功也不等价于消息发送成功，必须查看 Task 最终状态。

## 与研究流程串联

推荐调用方先等待研究 Task 的终态，再形成包含 Task ID、日期范围和结果位置的消息。失败通知应基于真实错误和日志，不要直接把“提交接受”写成“回测成功”。

通知是另一条独立 Task。若需要记录关系，可传入研究任务的 `source_tasks` 作为血缘信息，但通知实现不会主动读取上游结果或自动生成研究总结。

当前没有内置“通知所有任务完成”的统一开关。调度 Job 可以提交通知任务，但研究任务的等待和消息构造仍需显式编排。

## 失败与重复发送

缺少任一环境变量、群配置不是对象、群标识为空或钉钉请求失败都会使通知任务失败，查看 Task 日志确认具体阶段。

客户端逐群尝试并汇总失败；若部分群失败，其他群可能已经收到消息。重新运行可能再次发送到已成功群；当前没有以研究 Task ID 为键的通知幂等协议。通知任务成功与研究任务成功是两个独立事实。

## 相关文档与实现

- [研究流程](workflow.md)、[任务管理](../guides/task-management.md)
- [`通知 Task`](../../../axonx/task/builtins/dingtalk/task.py)
- [`钉钉客户端`](../../../axonx/task/builtins/dingtalk/client.py)
