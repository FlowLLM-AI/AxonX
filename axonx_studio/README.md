# AxonX Studio

AxonX 的本地任务工作台，提供运行状态管理和基于 Task JSON Schema 的动态提交表单。

## 开发

```bash
npm install
npm run dev
```

## 代码结构

- `src/app`：应用壳层、类型化 Hash 路由、导航、应用级类型和全局偏好。
- `src/features`：按业务能力隔离的页面、领域类型、数据转换和 Job API。
- `src/shared/api`：AxonX HTTP 协议、统一错误和强类型 SSE 事件。
- `src/shared`：其余无业务归属的 hooks、Schema 表单和 UI 基础组件。
- `src/styles`：主题 token、reset，以及按级联顺序拆分的基础、壳层、工作区、研究、运行时和 API 样式。

页面组件只负责组合展示。目标服务地址由 `AxonXClient` 选择；Job 请求体只包含业务参数。
领域协议类型由所属 feature 管理，
不得通过根目录聚合类型重新导出。

运行中的任务通过 `stream_task` 的 SSE 事件更新进度和日志，终态任务才按需读取日志文件。
Studio 只面向当前 AxonX 协议，不维护旧字段或旧请求格式兼容。

页面路由统一为 `#机器/页面/视图/资源`，例如
`#11.160.132.45:1024/task-defs/catalog`；本机使用 `local`，根地址默认进入首页。
机器列表提供完整目标地址，前端只传递目标参数，由后端解析配置和协议。

## 验证

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

Studio 始终使用同源 `/jobs` 接口；开发服务器通过 Vite 代理连接本机后端。
切换机器时仅发送 `target`，由后端读取 `targets` 配置及对应 token 转发普通请求、API 目录和事件流。
浏览器只保存本机服务 token，不保存远程 token。远程目标配置不正确时应修改后端配置。

## 构建并由 AxonX 托管

```bash
npm run build
cd ..
axonx start
```

AxonX 会自动发现 `axonx_studio/dist` 并通过同一个 HTTP 服务提供 Studio 与 API。

如果本机服务需要检查或同步其他目标服务，在 `.env` 中设置
`AXONX_TARGET=<host:port>` 和 `AXONX_SERVICE_TOKEN`，然后运行
`axonx start --config remote`。Studio 请求本机后端，由后端使用目标配置中的令牌连接所选服务。
