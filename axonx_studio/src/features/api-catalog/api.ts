import { axonx } from "../../shared/api/client";

export const listJobs = (target?: string, signal?: AbortSignal) =>
  axonx.jobs({ target, signal });

export const invokeApi = <T = unknown>(
  name: string,
  body: Record<string, unknown>,
  target?: string,
  signal?: AbortSignal,
) => axonx.invoke<T>(name, body, { target, signal });
