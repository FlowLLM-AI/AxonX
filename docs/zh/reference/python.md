# Python 参考

## 导入入口

```python
from axonx.app.core.application import Application
from axonx.app.config.loader import ConfigLoader
from axonx.app.steps.base import BaseStep
from axonx.app.components.registry import provider
from axonx.client.http import HttpClient, run_remote_job, stream_remote_job
from axonx.client.mcp import McpClient
from axonx.client.base import RemoteServiceError, RemoteConnectionError
from axonx.client.models import JobResponse, StagedFile
from axonx.client.events import ResultEvent
```

使用 Python 3.12+。根包导出版本元数据，能力命名空间不集中导出所有实现。

## 嵌入 Application

```python
import asyncio
from axonx.app.core.application import Application

async def main():
    async with Application(log_to_console=False, log_to_file=False) as app:
        print(app.is_started, app.workspace_path)

asyncio.run(main())
```

此最小图不需要产品适配器，不启动 HTTP 监听。加载已配置 Job 时，用 `ConfigLoader().resolve(config="default", log_config=False)` 解析并传入结果。使用相关能力时由宿主注入 TaskCatalog、更新后端或定时启动器。Task 客户端本身不需要 Application，Application 不自动加载 .env。

## Application 方法

`start()`、`close()` 按依赖管理生命周期。`run_job(name, arguments=None, *, target=None)` 返回 JobResponse；`stream_job(...)` 返回异步迭代器，不直接 await。两者要求应用已启动，转发目标必须列入 ApplicationConfig.targets。

## HTTP 客户端

```python
import asyncio
import os
from axonx.client.http import HttpClient

async def main():
    async with HttpClient(
        target="127.0.0.1:1024",
        token=os.environ["AXONX_SERVICE_TOKEN"],
        timeout=600.0,
    ) as client:
        response = await client.run_job("cli", {"argv": [
            "exec", "--task", "demo", "--task-name", "python-api",
            "--x", "1", "--y", "2",
        ]})
        if not response.success:
            raise RuntimeError(str(response.answer))
        assert response.answer["exit_code"] == 0
        status = await client.run_job("status", {
            "task_id": "base#demo#python-api", "detail": "full",
        })
        print(status.model_dump(mode="json"))

asyncio.run(main())
```

方法为 `run_job`、`stream_job`、`list_jobs`、`health`、`copy_file(Path, filename=None, directory=None)`、`discard_file(path)`。构造参数为 target、timeout、token 和可选 HTTP transport。用 async with 管理连接，凭据需显式传入，库客户端不会自动读取 CLI token 环境变量。远程 answer 是解码数据，本地 answer 可能含模型对象，需要时用 model_dump(mode="json") 统一。

## 消费事件

```python
from contextlib import aclosing
from axonx.client.events import ResultEvent

# Inside an async function with a started HttpClient named client:
async with aclosing(client.stream_job("stream_task", {"task_id": task_id})) as events:
    async for event in events:
        if isinstance(event, ResultEvent):
            print(event.response().model_dump(mode="json"))
        elif event.kind == "log":
            print(event.content, end="")
```

## 文件上传

`copy_file` 返回含 path、size、绝对 location 的 StagedFile。目标机插件安装使用 location，清理和同步使用 path。在 finally 中调用 discard_file。完整远程安装示例见[插件管理](../plugins/management.md)。

## MCP 客户端

`McpClient` 使用服务基础地址，通过 `/mcp` 提供 run_job、list_jobs、health，返回普通 Job 响应。实时事件使用 HTTP SSE，上传使用 HTTP。

## 一次性远程函数

`await run_remote_job("version", {}, target=..., token=...)` 打开并关闭一个 HTTP 客户端。`stream_remote_job` 是异步生成器，提前停止消费时用 aclosing 关闭。辅助函数不做 CLI 值转换。

## 错误与清理

RemoteConnectionError 表示无法连接或连接超时，RemoteServiceError 表示协议/HTTP 失败并含可选 status_code。另行检查 JobResponse.success。命令流中断可能无法判断是否已接受执行，重试前检查 Task 启动时间。取消会关闭连接，并可能终止服务拥有的 CLI 子进程。

源码：[Application](../../../axonx/app/core/application.py)、[HTTP](../../../axonx/client/http.py)、[MCP](../../../axonx/client/mcp.py)。
