# 客户端配置

连接配置独立于应用配置和执行配置。

## ConnectionOptions

`axonx.client.config.ConnectionOptions` 校验可选 target、正浮点 timeout（默认 60 秒）和可选非空 token。实例不可变并拒绝额外字段。CLI ClientOptions 增加 stream、stream_format（blocks 或 json）。

## 地址规则

目标为 HOST:PORT 或包含显式端口的 HTTP(S) 地址。末尾根斜杠会规范化；子路径、查询/片段、内嵌凭据和非法端口会被拒绝。传服务基础地址，不传 `/mcp` 或 Job 路由。Python 客户端省略 target 时先取 AXONX_SERVICE_TARGET，再取 http://127.0.0.1:1024。

## CLI token 来源

显式 --token 优先，否则本地 CLI 读取 AXONX_SERVICE_TOKEN，显式 --target 读取 AXONX_TARGET_TOKEN。CLI 加载 .env 但不替换已有环境变量。这些是客户端选项，不是公共 Job 参数。

## 显式 Python 连接

```python
from axonx.client.http import HttpClient
client = HttpClient(target="http://node-b:1024", token="replace-token", timeout=600.0)
```

用 async with 启动和关闭。Python HTTP/MCP 客户端需显式传 token，不自动发现 CLI token 变量。

## Studio 同源转发

Studio 使用本地服务，也可请求已配置的远程目标。后端按 ApplicationConfig.targets 解析地址和 token，调用方不能在业务参数中指定任意远程凭据。显式 CLI target 直接连接目标。

## 命令交接

Daemon/服务注入 AXONX_SERVICE_TARGET，供原生 CLI 子进程查询执行默认值。内部 AXONX_CLI_REQUEST_ID 关联响应完成回调并阻止嵌套转发/启动服务。执行身份保存在 Task metadata，不通过一组 Task 环境变量传输，不应伪造内部交接字段。

## 处理连接失败

只有连接失败允许本地 exec/kill 回退内置执行默认值。认证、协议、get_config 失败均向上传播。观察超时不代表 Task 失败，默认 cli Job 在连接取消后继续执行原生命令，重试前应检查当前 metadata。显式 Task kill 或服务关闭仍可停止执行。
