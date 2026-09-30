import type { JobCatalog, JobResponse } from "./types";

const configuredUrl = import.meta.env.VITE_AXONX_API_URL || "";
const tokenStorageKey = "axonx-service-token";
const memoryTokens = new Map<string, string>();

function storageKey(baseUrl: string): string {
  return baseUrl
    ? `${tokenStorageKey}:${baseUrl.replace(/\/$/, "")}`
    : tokenStorageKey;
}

function storedToken(baseUrl: string): string {
  const key = storageKey(baseUrl);
  try {
    return localStorage.getItem(key)?.trim() || "";
  } catch {
    return memoryTokens.get(key) || "";
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
  readonly baseUrl: string;

  constructor(
    baseUrl = configuredUrl,
    private token = storedToken(baseUrl),
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  setToken(token: string): void {
    this.token = token.trim();
    const key = storageKey(this.baseUrl);
    try {
      if (this.token) localStorage.setItem(key, this.token);
      else localStorage.removeItem(key);
    } catch {
      if (this.token) memoryTokens.set(key, this.token);
      else memoryTokens.delete(key);
    }
  }

  hasToken(): boolean {
    return Boolean(this.token);
  }

  forBaseUrl(baseUrl: string): AxonXClient {
    return new AxonXClient(baseUrl);
  }

  private headers(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    return headers;
  }

  forTarget(target: string): AxonXClient {
    const url = target.includes("://")
      ? target
      : `${this.baseUrl ? new URL(this.baseUrl).protocol : window.location.protocol}//${target}`;
    return this.forBaseUrl(url);
  }

  invocation(arguments_: Record<string, unknown>) {
    return { arguments: arguments_ };
  }

  async invoke<T>(
    name: string,
    arguments_: Record<string, unknown> = {},
    options: RequestOptions = {},
  ): Promise<T> {
    const client = options.target ? this.forTarget(options.target) : this;
    const response = await fetch(
      `${client.baseUrl}/jobs/${encodeURIComponent(name)}`,
      {
        method: "POST",
        headers: client.headers({ "Content-Type": "application/json" }),
        body: JSON.stringify(this.invocation(arguments_)),
        signal: options.signal,
      },
    );
    return readJobResponse<T>(response);
  }

  async jobs(signal?: AbortSignal): Promise<JobCatalog> {
    const response = await fetch(`${this.baseUrl}/jobs`, {
      headers: this.headers(),
      signal,
    });
    return readJobResponse<JobCatalog>(response);
  }

  eventsUrl(name: string): string {
    return `${this.baseUrl}/jobs/${encodeURIComponent(name)}/events`;
  }

  requestHeaders(extra?: HeadersInit): Headers {
    return this.headers(extra);
  }
}

export const axonx = new AxonXClient();

export function clientForTarget(target?: string): AxonXClient {
  if (!target) return axonx;
  return axonx.forTarget(target);
}
