# 机器 API

查询版本、已配置目标健康与机器资源，或在所选服务机器执行命令。target 属于 HTTP 请求封装或 CLI 连接选项，不属于这些 Job 的业务字段。

![机器 API调用示意](../../figures/api/machine-target.svg)

## 调用约定

以下均为 `POST /jobs/{name}`，请求体是 `{"arguments":{...}}`。远程转发时在封装顶层添加 `target`，不能放进 arguments。每个响应使用 [JobResponse](overview.md#响应与错误)，表格默认值依据当前内置配置和 Step。部署可修改 Job Schema，运行服务的 `/jobs` 是最终依据。

所有示例 JSON 均为结构示例；任务、会话、文件路径与哈希必须替换为本服务实际返回的值。完整通用 TaskStatus 字段见 [Task 协议](../reference/task-contracts.md)。

## 接口清单

| Job              | 用途                                             |
| ---------------- | ------------------------------------------------ |
| `version`        | 读取安装包的版本。                               |
| `list_machines`  | 检查全部配置的 targets 健康。                    |
| `machine_status` | 采样服务机器资源。                               |
| `python`         | 使用所选服务的 Python 环境执行多行 Python 代码。 |

## version

读取安装包的版本。

无公开业务参数；使用 `{"arguments":{}}`。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

answer 是版本字符串，metadata.version 同时提供该版本。

```json
{
  "answer": "0.1.0",
  "success": true,
  "metadata": { "version": "0.1.0" }
}
```

**行为与失败情况**

版本值仅为示例；构建分支/提交信息从 machine_status 查看。

## list_machines

检查全部配置的 targets 健康。

无公开业务参数；使用 `{"arguments":{}}`。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

answer 为 MachineHealth 数组，每项 address、healthy。

```json
{
  "answer": [
    {
      "address": "http://node-b:1024",
      "healthy": true
    }
  ],
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

默认 targets=[] 因而结果为空。healthy=false 可能是网络、token 或服务异常，不等价于资源不足。

## machine_status

采样服务机器资源。

无公开业务参数；使用 `{"arguments":{}}`。

**请求**

```json
{
  "arguments": {}
}
```

**响应**

answer 为 MachineInfo：axonx、cpu、memory、gpus。

```json
{
  "answer": {
    "axonx": {
      "version": "0.1.0",
      "git_commit": null,
      "git_branch": null
    },
    "cpu": {
      "total_cores": 8,
      "physical_cores": 4,
      "usage_percent": 12.0
    },
    "memory": {
      "total_bytes": 16000000000,
      "used_bytes": 4000000000,
      "available_bytes": 12000000000,
      "usage_percent": 25.0
    },
    "gpus": []
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

cpu 的 total_cores/physical_cores 可为 null；内存单位字节。GPU vendor 仅 nvidia/amd，探测命令不可用或无设备时列表可为空；不承诺检测 Apple GPU。

## python

在所选服务机器上，用服务自身的解释器（`sys.executable`）及已安装依赖启动独立子进程执行 Python 源码。源码通过 stdin 传入，不受命令行长度限制。每次调用的 Python 变量独立，继承服务的工作目录和环境，以服务用户的权限运行。

| 参数      | 类型   | 必填 | 默认值      | 约束与含义                                                          |
| --------- | ------ | ---- | ----------- | ------------------------------------------------------------------- |
| `code`    | string | 是   | `—（省略）` | 支持换行的 Python 源码；minLength=1。用 print 将结果输出至 stdout。 |
| `timeout` | number | 否   | `30`        | 执行超时秒数；exclusiveMinimum=0、maximum=300。                     |

调用 `POST /jobs/python`：

```json
{
  "arguments": {
    "code": "from pathlib import Path\nprint(Path.cwd())",
    "timeout": 30
  }
}
```

MCP 客户端按发现的 Schema 将 `code` 作为普通多行字符串传入。JSON 仍需正常的字符串转义。CLI 示例：`axonx python --code 'print(1 + 1)' --timeout 30`。远程执行使用请求顶层 `target` 或 CLI `--target`。

**响应**

`answer` 为 PythonOutput，包含 stdout、stderr、exit_code、stdout_truncated、stderr_truncated。执行在超时前完成且退出码为零时，`success=true`。

```json
{
  "answer": {
    "stdout": "/srv/axonx\n",
    "stderr": "",
    "exit_code": 0,
    "stdout_truncated": false,
    "stderr_truncated": false
  },
  "success": true,
  "metadata": {}
}
```

**行为与失败情况**

每个输出流最多保留 1 MiB，超出的输出会丢弃，并设置对应的截断标记。Python 异常和语法错误返回 `success=false`、非零 `exit_code`，错误信息写入 `stderr`。超时返回 `success=false`、`exit_code=null`，保留已捕获的输出，并在 `stderr` 中追加超时说明。超时或取消会终止进程组、关闭输入输出管道，并回收主进程，无需等待脱离进程组的子进程关闭继承的管道。

内置 Agent 默认的 `job_tools` 名单不暴露 `python`。启用该 Agent 的 Python 执行时，将其加入 `components.agent.default.job_tools`；外部 MCP 暴露范围由服务的 Job 目录决定。

## 失败响应示例

Python 的非零退出与超时都是正常协议返回的业务失败。请求 `code="import sys; sys.exit(3)"` 时：

```json
{
  "answer": {
    "stdout": "",
    "stderr": "",
    "exit_code": 3,
    "stdout_truncated": false,
    "stderr_truncated": false
  },
  "success": false,
  "metadata": {}
}
```

超时时 exit_code=null；stderr 包含 `Command timed out after ... seconds`。timeout=0 或 timeout>300 则在 Schema 校验阶段返回 HTTP 422。list_machines 中某个目标 healthy=false 不会让整次列表查询自动失败，应逐台解释结果。

## 相关文档

- [协议、鉴权与错误](overview.md)
- [远程机器](../guides/remote-machines.md)
- [CLI 参考](../reference/cli.md)
- [事件协议](events.md)

实现依据：`axonx/config/default.yaml`、`axonx/steps/machine/` 与 `axonx/components/service/http/jobs.py`。
