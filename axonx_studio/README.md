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

页面组件只负责组合展示。业务参数不得包含 `remote_ip`；远程节点属于请求选项，
由 `AxonXClient` 写入 Job invocation envelope。领域协议类型由所属 feature 管理，
不得通过根目录聚合类型重新导出。

运行中的任务通过 `stream_task` 的 SSE 事件更新进度和日志，终态任务才按需读取日志文件。
Studio 只面向当前 AxonX 协议，不维护旧字段或旧请求格式兼容。

## 验证

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

开发服务器默认将 `/health` 和 `/jobs` 代理到 `http://127.0.0.1:1024`。可以通过
`VITE_AXONX_API_URL` 使用其他服务地址。
受保护的服务可通过 `VITE_AXONX_TOKEN` 配置 Bearer token。

## 构建并由 AxonX 托管

```bash
npm run build
cd ..
axonx start
```

AxonX 会自动发现 `axonx_studio/dist` 并通过同一个 HTTP 服务提供 Studio 与 API。
