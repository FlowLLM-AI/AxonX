# AxonX Studio

AxonX 的本地任务工作台，提供运行状态管理和基于 Task JSON Schema 的动态提交表单。

## 开发

```bash
npm install
npm run dev
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
