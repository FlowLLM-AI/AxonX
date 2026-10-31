import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

export default defineConfig(({ mode }) => {
  const workspaceRoot = fileURLToPath(new URL("..", import.meta.url));
  const env = loadEnv(mode, workspaceRoot, "");
  const backend = env.AXONX_DEV_SERVER || "http://127.0.0.1:1024";
  const version = readFileSync(
    new URL("../axonx/_version.py", import.meta.url),
    "utf8",
  ).match(/^__version__ = "([^"]+)"$/m)![1];
  return {
    define: { "import.meta.env.VITE_AXONX_VERSION": JSON.stringify(version) },
    base:
      mode === "playground" ? `${env.DOCS_BASE || "/AxonX/"}playground/` : "/",
    build: {
      outDir: mode === "playground" ? "dist-playground" : "dist",
      target: "es2022",
    },
    plugins: [react()],
    envDir: workspaceRoot,
    server: {
      port: 4173,
      proxy: {
        "/health": backend,
        "/jobs": backend,
        "/upload": backend,
        "/mcp": backend,
        "/proxy": backend,
      },
    },
  };
});
