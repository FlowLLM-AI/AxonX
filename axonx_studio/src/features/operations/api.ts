import { axonx } from "../../shared/api/client";
import type { StudioPage } from "../../shared/api/contracts";

export const listStudioPages = (target?: string, signal?: AbortSignal) =>
  axonx.invoke<StudioPage[]>("list_studio_pages", {}, { target, signal });
