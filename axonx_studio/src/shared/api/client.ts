import type { JobCatalog, JobResponse } from "./types";

const configuredUrl = import.meta.env.VITE_AXONX_API_URL || "";
// Vite maps the workspace-level AXONX_SERVICE_TOKEN to this private build
// constant, so local Studio and AxonX share one configuration source.
const configuredToken = import.meta.env.VITE_AXONX_TOKEN || "";

export interface RequestOptions {
  signal?: AbortSignal;
  remoteIp?: string;
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
    private readonly token = configuredToken,
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private headers(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (this.token) headers.set("Authorization", `Bearer ${this.token}`);
    return headers;
  }

  invocation(arguments_: Record<string, unknown>, remoteIp?: string) {
    return {
      arguments: arguments_,
      ...(remoteIp ? { remote_ip: remoteIp } : {}),
    };
  }

  async invoke<T>(
    name: string,
    arguments_: Record<string, unknown> = {},
    options: RequestOptions = {},
  ): Promise<T> {
    const response = await fetch(
      `${this.baseUrl}/jobs/${encodeURIComponent(name)}`,
      {
        method: "POST",
        headers: this.headers({ "Content-Type": "application/json" }),
        body: JSON.stringify(this.invocation(arguments_, options.remoteIp)),
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

export function clientForAddress(address?: string): AxonXClient {
  if (!address) return axonx;
  return new AxonXClient(`${window.location.protocol}//${address}`);
}
