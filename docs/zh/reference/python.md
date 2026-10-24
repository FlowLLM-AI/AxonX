# Python 调用参考

Python 可以在进程内嵌入 Application，或连接已经运行的 HTTP/MCP 服务。两种路径都返回 JobResponse，但生命周期、配置和执行位置不同。这里使用当前公开导出的类与函数。

![本地应用与远程客户端](../../figures/reference/python-paths.svg)

## 内部导入路径迁移

内部模块路径已调整，不保留旧兼容包。顶层公开类仍可导入，并按需加载。请使用以下规范路径；Task 元数据和网络数据模型保持一致。

| 原路径                                          | 规范路径                                                  |
| ----------------------------------------------- | --------------------------------------------------------- |
| `axonx.components / axonx.steps / axonx.core`   | `axonx.app.components / axonx.app.steps / axonx.app.core` |
| `axonx.plugin_kit / axonx.common.registry`      | `axonx.plugin / axonx.plugin.registry`                    |
| `axonx.enums / axonx.common.enums`              | `axonx.task.enums / axonx.app.components.types`           |
| `axonx.common.command`                          | `axonx.cli.parser / axonx.config.target`                  |
| `axonx.config.ApplicationConfig / StudioPage`   | `axonx.app.config`                                        |
| `axonx.common.utils.env / target`               | `axonx.config.env / target`                               |
| `axonx.common.utils.build_info / log_retention` | `axonx.app.core.build_info / logging`                     |
| `axonx.common.utils.logging.task_log_scope`     | `axonx.task.runtime.logging`                              |
| `axonx.common.utils / fs / async_work`          | `axonx.common.logging / fs / async_work`                  |
| `axonx.task.artifact / status / source`         | `axonx.task.schemas.artifact / lifecycle`                 |
| `axonx.task.protocol`                           | `axonx.task.schemas.protocol / model / prediction`        |

Task 执行器直接接收任务名和输入参数，不接收 CLI Command，也不再套一层输出包装：

```python
from axonx.task.runtime import TaskExecutor

status = TaskExecutor(".axonx").execute("demo", {"x": 2, "y": 3})
print(status.output_params)
```

## 导入入口

```python
from axonx import Application, BaseStep, provider
from axonx.config import resolve_app_config
from axonx.app.components.client import HttpClient, McpClient, RemoteServiceError
from axonx.app.core import run_remote_job, stream_remote_job
from axonx.app.components.job import ResultEvent
```

Application 从顶层导出；HTTP/MCP 客户端与事件类型从各自子包导出。项目使用 Python 3.12 语法，不能用较旧解释器直接导入。

## 嵌入 Application

```python
import asyncio
from axonx import Application
from axonx.config import resolve_app_config

async def main():
    config = resolve_app_config(log_config=False, config="default")
    async with Application(**config) as app:
        response = await app.run_job("version", {})
        if not response.success:
            raise RuntimeError(str(response.answer))
        print(response.model_dump(mode="json"))

asyncio.run(main())
```

async with 按依赖顺序启动组件和 Job，退出时反序关闭；嵌入式 Application 不启动 daemon 或 cron worker，这些进程由 CLI start 管理。这个例子不启动 HTTP 监听；service 的 run_app 由 CLI start 调用。加载 default 会装配其中组件，调用者需要当前环境可导入对应依赖；最小应用可只保留需要的 Job。

Application 不自动读取 .env；resolve_app_config 只展开已存在的环境变量。若需要 .env 先用应用自己的环境加载方式。

## Application 方法

| 方法                                             | 参数                           | 返回与限制                            |
| ------------------------------------------------ | ------------------------------ | ------------------------------------- |
| start()                                          | 无                             | await，幂等启动                       |
| close()                                          | 无                             | await，反序清理；多清理错误可能聚合   |
| run_job(name, arguments=None, *, target=None)    | Job 名、参数映射、可选配置目标 | await 返回 JobResponse                |
| stream_job(name, arguments=None, *, target=None) | 同上                           | 返回 AsyncIterator，不 await 方法本身 |

run_job 与 stream_job 均要求应用已启动。target 非空时必须在 ApplicationConfig.targets 中，使用其中地址/token；本机调用不受 HTTP public_jobs 筛选限制，但仍校验业务 Schema 与系统保留字段。

## HTTP 客户端

```python
import asyncio
import os
from axonx.app.components.client import HttpClient

async def main():
    async with HttpClient(
        target="127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=600.0,
    ) as client:
        definitions = await client.run_job("get_task_definition", {"task": "demo"})
        if not definitions.success:
            raise RuntimeError(str(definitions.answer))
        completed = await client.run_job("cli", {
            "argv": ["exec", "--task", "demo", "--x", "1", "--y", "2",
                     "--task-name", "python-demo"],
        })
        if not completed.success:
            raise RuntimeError(str(completed.answer))
        print(completed.answer["exit_code"], completed.answer["stdout"])

asyncio.run(main())
```

远程 answer 是解码后的字典/列表；本机 Application.answer 也可能保留 Pydantic/dataclass 对象。要统一处理，先调用 response.model_dump(mode="json")，不要假定两条路径中的 answer 都具有同一 Python 对象类型。

| HttpClient 方法 | 签名要点                            | 返回                    |
| --------------- | ----------------------------------- | ----------------------- |
| run_job         | name, arguments=None                | JobResponse             |
| stream_job      | name, arguments=None                | AsyncIterator[JobEvent] |
| list_jobs       | 无                                  | list[JobInfo]           |
| health          | 无                                  | bool，失败折叠 false    |
| copy_file       | Path，filename=None，directory=None | StagedFile              |
| discard_file    | path: str                           | 清理的路径字符串        |

构造参数 target=None、timeout=60.0、token=None；可选 transport 用于注入 HTTP 传输（例如测试）。进入 async with 后才可调用。target 不含 `/mcp` 或 Job 子路径。

## 事件消费

```python
async with HttpClient(target="127.0.0.1:1024", token=token, timeout=600.0) as client:
    async for event in client.stream_job("stream_task", {"task_id": task_id}):
        if isinstance(event, ResultEvent):
            response = event.response()
            print(response.success, response.answer)
        elif event.kind == "log":
            print(event.content, end="")
```

这是异步函数内的片段，token/task_id 来自配置与 Task metadata。详细 framing 与断线规则见 [SSE](../api/events.md)。对提前停止消费的异步生成器，使用 contextlib.aclosing 保证关闭事件源。

## 文件上传

`HttpClient.copy_file` 以原始二进制流上传到 `/upload`，通过请求头提供文件名与可选暂存目录。直接 HTTP 调用也可使用 multipart，两种格式返回相同的 StagedFile。见[文件上传与清理](../api/workspace.md#文件上传与清理)。

```python
from pathlib import Path

async with HttpClient(target=target, token=token) as client:
    copied = await client.copy_file(Path("dist/axonx_example-0.1.0-py3-none-any.whl"))
    try:
        installed = await client.run_job("cli", {
            "argv": ["plugin", "install", copied.location],
        })
        print(installed.model_dump(mode="json"))
    finally:
        await client.discard_file(copied.path)
```

这是安装流程片段，执行前需确认制品。copy_file 分块读取并上传，不把服务相对路径当成客户端文件路径。重复 discard_file 可清理已消费的暂存位置。

## MCP 客户端

```python
async with McpClient(target=target, token=token, timeout=60.0) as client:
    print(await client.health())
    jobs = await client.list_jobs()
    response = await client.run_job("list_task_ids", {})
    print(response.model_dump(mode="json"))
```

McpClient 的 health 使用 MCP ping；list_jobs 根据工具 Schema 生成 JobInfo；run_job 从 structured_content/data 校验 JobResponse。它没有 stream_job、copy_file 或 discard_file，实时事件和字节传输用 HttpClient。

## 一次性远程函数

```python
response = await run_remote_job(
    "version", {}, target="node-b:1024", token=token, timeout=60.0
)
async for event in stream_remote_job(
    "stream_task", {"task_id": task_id},
    target="node-b:1024", token=token, timeout=600.0,
):
    print(event.model_dump(mode="json"))
```

arguments 是必填映射，每次创建并关闭 HttpClient。频繁查询用长生命周期客户端，避免反复连接。这个 target 是直连地址，不依赖本机 Application 的 targets。

## 错误与清理

```python
try:
    async with HttpClient(target=target, token=token) as client:
        response = await client.run_job("status", {"task_id": task_id})
except RemoteServiceError as exc:
    print("连接或协议失败", exc.status_code, str(exc))
else:
    if not response.success:
        print("业务失败", response.answer)
```

Task 执行与进程控制由 CLI 执行环境负责。服务通过 TaskRepository 读取已发布 metadata，不取消、恢复或接管 Task 进程。

## 相关文档

- [客户端配置](client-configuration.md)
- [API 总览](../api/overview.md)
- [框架扩展](../development/framework-extensions.md)

实现依据：`axonx/__init__.py`、`core/application.py`、`core/dispatch.py`、`components/client/`。
