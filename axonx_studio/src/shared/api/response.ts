import { isAbortError } from "../lib/errors";
import type { JobResponse } from "./types";

export class AxonXError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "AxonXError";
  }
}

export function jobAnswer<T>(payload: unknown, status?: number): T {
  if (
    !payload ||
    typeof payload !== "object" ||
    !("success" in payload) ||
    typeof payload.success !== "boolean" ||
    !("answer" in payload)
  )
    throw new AxonXError("Invalid AxonX response envelope", status);
  const result = payload as JobResponse<T>;
  if (!result.success)
    throw new AxonXError(String(result.answer ?? "Job failed"), status);
  return result.answer;
}

export async function readJobResponse<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (reason) {
    if (isAbortError(reason)) throw reason;
    throw new AxonXError(
      `Invalid server response (HTTP ${response.status})`,
      response.status,
    );
  }
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
  return jobAnswer<T>(payload, response.status);
}
