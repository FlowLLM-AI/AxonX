import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const workspaceRoot = fileURLToPath(new URL("..", import.meta.url));
  const env = loadEnv(mode, workspaceRoot, "");
  const backend = env.AXONX_DEV_SERVER || "http://127.0.0.1:1024";
  return {
    plugins: [react()],
    envDir: workspaceRoot,
    define: {
      "import.meta.env.VITE_AXONX_TOKEN": JSON.stringify(
        env.AXONX_SERVICE_TOKEN || "",
      ),
    },
    server: {
      port: 4173,
      proxy: {
        "/health": backend,
        "/jobs": backend,
        "/files": backend,
        "/mcp": backend,
        "/proxy": backend,
      },
    },
  };
});
