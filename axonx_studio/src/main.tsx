import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./i18n";
import "./styles/index.css";
import "./styles/reset.css";
import "./styles/tokens.css";

if (import.meta.env.MODE === "playground") {
  const { createPlayground } = await import("./playground/runtime");
  const { AxonXClient, configureClient } = await import("./shared/api/client");
  configureClient(new AxonXClient(createPlayground(), false));
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
