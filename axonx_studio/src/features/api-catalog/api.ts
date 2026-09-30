import { clientForTarget } from "../../shared/api/client";
import type { JobCatalog } from "../../shared/api/types";

export const listJobs = (target?: string, signal?: AbortSignal) =>
  clientForTarget(target).jobs(signal) as Promise<JobCatalog>;

export const invokeApi = <T = unknown>(
  name: string,
  body: Record<string, unknown>,
  target?: string,
  signal?: AbortSignal,
) => clientForTarget(target).invoke<T>(name, body, { signal });
