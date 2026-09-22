import { clientForAddress } from "../../shared/api/client";
import type { JobCatalog } from "../../shared/api/types";

export const listJobs = (remoteAddress?: string, signal?: AbortSignal) =>
  clientForAddress(remoteAddress).jobs(signal) as Promise<JobCatalog>;

export const invokeApi = <T = unknown>(
  name: string,
  body: Record<string, unknown>,
  remoteAddress?: string,
  signal?: AbortSignal,
) => clientForAddress(remoteAddress).invoke<T>(name, body, { signal });
