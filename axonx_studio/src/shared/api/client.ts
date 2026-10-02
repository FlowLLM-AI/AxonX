import type { JobCatalog, JobResponse } from "./types";

const tokenStorageKey = "axonx-service-token";

function storedToken(): string {
  try {
    return localStorage.getItem(tokenStorageKey)?.trim() || "";
  } catch {
    return "";
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  target?: string;
}

export class AxonXError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "AxonXError";
  }
}

async function decode(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new AxonXError(
      `Invalid server response (HTTP ${response.status})`,
      response.status,
    );
  }
}

export async function readJobResponse<T>(response: Response): Promise<T> {
  const payload = await decode(response);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : undefined;
    throw new AxonXError(
      typeof detail === "string"
        ? detail
        : detail == null
          ? `HTTP ${response.status}`
          : JSON.stringify(detail),
      response.status,
    );
  }
  if (!payload || typeof payload !== "object" || !("success" in payload))
    throw new AxonXError("Invalid AxonX response envelope", response.status);
  const result = payload as JobResponse<T>;
  if (!result.success)
    throw new AxonXError(
      String(result.answer || "Job failed"),
      response.status,
    );
  return result.answer;
}

export class AxonXClient {
  private token = storedToken();

  setToken(token: string): void {
    this.token = token.trim();
    try {
      if (this.token) localStorage.setItem(tokenStorageKey, this.token);
      else localStorage.removeItem(tokenStorageKey);
    } catch {
      // Keep the token in memory when browser storage is unavailable.
    }
  }

  hasToken(): boolean {
    return Boolean(this.token);
  }

  requestHeaders(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    return headers;
  }

  invocation(arguments_: Record<string, unknown>, target?: string) {
    return { arguments: arguments_, target };
  }

  async invoke<T>(
    name: string,
    arguments_: Record<string, unknown> = {},
    options: RequestOptions = {},
  ): Promise<T> {
    const response = await fetch(`/jobs/${encodeURIComponent(name)}`, {
      method: "POST",
      headers: this.requestHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(this.invocation(arguments_, options.target)),
      signal: options.signal,
    });
    return readJobResponse<T>(response);
  }

  async jobs(options: RequestOptions = {}): Promise<JobCatalog> {
    const query = options.target
      ? `?${new URLSearchParams({ target: options.target })}`
      : "";
    const response = await fetch(`/jobs${query}`, {
      headers: this.requestHeaders(),
      signal: options.signal,
    });
    return readJobResponse<JobCatalog>(response);
  }

  eventsUrl(name: string): string {
    return `/jobs/${encodeURIComponent(name)}/events`;
  }
}

export const axonx = new AxonXClient();
