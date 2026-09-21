import {
  AxonXError,
  readJobResponse,
  type AxonXClient,
  type RequestOptions,
} from "./client";
import type { JobResponse } from "./types";

export interface ProgressEvent {
  kind: "progress";
  name: string;
  started_at: string | null;
  finished_at: string | null;
  percentage: number | null;
}

export interface LogEvent {
  kind: "log";
  content: string;
  start_offset: number;
  next_offset: number;
  file_size: number;
  has_more_before: boolean;
  has_more_after: boolean;
  reset: boolean;
  channel: string;
}

export interface ArtifactEvent {
  kind: "artifact";
  path: string;
  sha256: string;
  size: number;
  media_type: string | null;
  extra: Record<string, unknown>;
}

export interface AgentBlockPatch {
  operation: "start" | "append" | "replace" | "finish";
  block_id: string;
  block_type: "thinking" | "text" | "tool" | "system" | "error";
  delta: string;
  payload: Record<string, unknown>;
}

export interface AgentMessageEvent {
  kind: "agent_message";
  session_id: string;
  type_name: string;
  message: Record<string, unknown>;
  sequence: number;
  presentation: AgentBlockPatch[];
}

export interface ResultEvent<T = unknown> extends JobResponse<T> {
  kind: "result";
}

export type JobEvent<T = unknown> =
  | ProgressEvent
  | LogEvent
  | ArtifactEvent
  | AgentMessageEvent
  | ResultEvent<T>;

export interface StreamOptions<T> extends RequestOptions {
  onEvent?: (event: JobEvent<T>) => void;
}

function eventData(frame: string): string {
  return frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6))
    .join("\n");
}

export async function streamJob<T>(
  client: AxonXClient,
  name: string,
  arguments_: Record<string, unknown>,
  options: StreamOptions<T> = {},
): Promise<T> {
  const response = await fetch(client.eventsUrl(name), {
    method: "POST",
    headers: client.requestHeaders({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(client.invocation(arguments_, options.remoteIp)),
    signal: options.signal,
  });
  if (!response.ok) await readJobResponse(response);
  if (!response.body)
    throw new AxonXError("Event stream returned no body", response.status);
  if (!response.headers.get("Content-Type")?.startsWith("text/event-stream"))
    throw new AxonXError("Server returned a non-event-stream response");

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = eventData(frame);
        if (!data) continue;
        const event = JSON.parse(data) as JobEvent<T>;
        options.onEvent?.(event);
        if (event.kind === "result") {
          if (!event.success) throw new AxonXError(String(event.answer));
          await reader.cancel();
          return event.answer;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
  throw new AxonXError("Event stream ended without a terminal result");
}
