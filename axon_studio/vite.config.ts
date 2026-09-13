import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.AXONX_DEV_SERVER || "http://127.0.0.1:1024";
  return {
    plugins: [react()],
    server: {
      port: 4173,
      proxy: { "/health": backend, "/jobs": backend },
    },
  };
});
