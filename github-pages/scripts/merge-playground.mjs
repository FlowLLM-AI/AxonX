import { cp, rm } from "node:fs/promises";
const output = new URL("../dist/playground/", import.meta.url);
await rm(output, { recursive: true, force: true });
await cp(
  new URL("../../axonx_studio/dist-playground/", import.meta.url),
  output,
  { recursive: true },
);
