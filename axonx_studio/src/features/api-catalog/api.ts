import {
  parseJobResponse,
  parseJsonResponse,
  remoteBase,
} from "../../shared/api/client";
import type { JobInfo } from "../../types";

export const listJobs = (remoteAddress?: string, signal?: AbortSignal) =>
  fetch(`${remoteBase(remoteAddress)}/jobs`, { signal }).then(
    parseJsonResponse<JobInfo[]>,
  );

export const invokeApi = <T = unknown>(
  name: string,
  body: Record<string, unknown>,
  remoteAddress?: string,
  signal?: AbortSignal,
) =>
  fetch(`${remoteBase(remoteAddress)}/jobs/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(parseJobResponse<T>);
