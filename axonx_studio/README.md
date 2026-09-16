# AxonX Studio

AxonX 的本地任务工作台，提供运行状态管理和基于 Task JSON Schema 的动态提交表单。

## 开发

```bash
npm install
npm run dev
```

## 代码结构

- `src/app`：应用壳层、类型化 Hash 路由、导航和全局偏好。
- `src/features`：按业务能力隔离的页面、领域类型和 API。
- `src/shared`：无业务归属的请求客户端、hooks、Schema 表单和 UI 基础组件。
- `src/styles`：主题 token 与全局基础样式；功能样式仍由对应的语义化 class 管理。

页面组件只负责组合展示。请求协议、字段转换、轮询、复制反馈和格式化逻辑应放在所属 feature 或 `shared` 中，避免在页面内重复实现。

## 验证

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

开发服务器默认将 `/health` 和 `/jobs` 代理到 `http://127.0.0.1:1024`。可以通过
`VITE_AXONX_API_URL` 使用其他服务地址。

## 构建并由 AxonX 托管

```bash
npm run build
cd ..
axonx start
```

AxonX 会自动发现 `axonx_studio/dist` 并通过同一个 HTTP 服务提供 Studio 与 API。
