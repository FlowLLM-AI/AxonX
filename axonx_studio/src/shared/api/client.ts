import type { ApiResponse } from "../../types";

const configuredUrl = import.meta.env.VITE_AXONX_API_URL || "";
export const API_URL = configuredUrl.replace(/\/$/, "");

async function json(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`Invalid server response (HTTP ${response.status})`);
  }
}

export async function parseJobResponse<T>(response: Response): Promise<T> {
  const payload = (await json(response)) as
    ApiResponse<T> | { detail?: unknown };
  if (!response.ok) {
    const detail = "detail" in payload ? payload.detail : undefined;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `HTTP ${response.status}`,
    );
  }
  const result = payload as ApiResponse<T>;
  if (!result.success)
    throw new Error(String(result.answer || "Request failed"));
  return result.answer;
}

export async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await json(response);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? payload.detail
        : undefined;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `HTTP ${response.status}`,
    );
  }
  return payload as T;
}

export async function callJob<T>(
  name: string,
  body: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<T> {
  return fetch(`${API_URL}/jobs/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }).then(parseJobResponse<T>);
}

export function remoteBody(remoteIp?: string): Record<string, string> {
  return remoteIp ? { remote_ip: remoteIp } : {};
}

export function remoteBase(remoteAddress?: string): string {
  return remoteAddress
    ? `${window.location.protocol}//${remoteAddress}`
    : API_URL;
}
