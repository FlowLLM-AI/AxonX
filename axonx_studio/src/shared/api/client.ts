import { playground } from "../../app/environment";
import { readJobEvents, type StreamOptions } from "./event";
import { readJobResponse } from "./response";
import type { JobCatalog } from "./types";

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

export type Transport = (url: string, init?: RequestInit) => Promise<Response>;

export class AxonXClient {
  constructor(
    private readonly transport: Transport = (url, init) => fetch(url, init),
    private readonly authentication = true,
  ) {
    this.token = authentication ? storedToken() : "";
  }

  private token: string;
  private revision = 0;

  get authRevision(): number {
    return this.revision;
  }

  setToken(token: string): void {
    if (!this.authentication) return;
    const next = token.trim();
    if (next !== this.token) this.revision += 1;
    this.token = next;
    try {
      if (this.token) localStorage.setItem(tokenStorageKey, this.token);
      else localStorage.removeItem(tokenStorageKey);
    } catch {
      // Keep the token in memory when browser storage is unavailable.
    }
  }

  hasToken(): boolean {
    return Boolean(this.authentication && this.token);
  }

  requestHeaders(extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    const token = this.authentication ? this.token : "";
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return headers;
  }

  private requestJob(
    name: string,
    arguments_: Record<string, unknown>,
    options: RequestOptions,
    streaming = false,
  ): Promise<Response> {
    return this.transport(
      `/jobs/${encodeURIComponent(name)}${streaming ? "/events" : ""}`,
      {
        method: "POST",
        headers: this.requestHeaders({
          "Content-Type": "application/json",
          ...(streaming ? { Accept: "text/event-stream" } : {}),
        }),
        body: JSON.stringify({ arguments: arguments_, target: options.target }),
        signal: options.signal,
      },
    );
  }

  async invoke<T = unknown>(
    name: string,
    arguments_: Record<string, unknown> = {},
    options: RequestOptions = {},
  ): Promise<T> {
    const response = await this.requestJob(name, arguments_, options);
    return readJobResponse<T>(response);
  }

  async stream<T = unknown>(
    name: string,
    arguments_: Record<string, unknown> = {},
    options: StreamOptions<T> = {},
  ): Promise<T> {
    const response = await this.requestJob(name, arguments_, options, true);
    return readJobEvents<T>(response, options.onEvent);
  }

  async jobs(options: RequestOptions = {}): Promise<JobCatalog> {
    const query = options.target
      ? `?${new URLSearchParams({ target: options.target })}`
      : "";
    const response = await this.transport(`/jobs${query}`, {
      headers: this.requestHeaders(),
      signal: options.signal,
    });
    return readJobResponse<JobCatalog>(response);
  }
}

export let axonx = new AxonXClient(undefined, !playground);

export function configureClient(client: AxonXClient) {
  axonx = client;
}
