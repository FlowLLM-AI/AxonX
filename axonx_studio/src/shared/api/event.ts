import {
  AxonXError,
  readJobResponse,
  type AxonXClient,
  type RequestOptions,
} from "./client";
import type { LogEvent } from "./contracts";
import type { JobResponse } from "./types";

import type { TaskStepStatus as StepContract } from "./contracts";
/** Presentation also accepts partial live progress snapshots. */
export type TaskStepStatus = Pick<
  StepContract,
  "name" | "started_at" | "finished_at" | "percentage"
> &
  Partial<StepContract>;

export type { ProgressEvent, ArtifactEvent, LogEvent } from "./contracts";
import type { ProgressEvent, ArtifactEvent } from "./contracts";

export type { AgentBlockPatch, AgentMessageEvent } from "./contracts";
import type { AgentMessageEvent } from "./contracts";

export interface ResultEvent<T = unknown> extends JobResponse<T> {
  kind: "result";
}

export type JobEvent<T = unknown> =
  ProgressEvent | LogEvent | ArtifactEvent | AgentMessageEvent | ResultEvent<T>;

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
  const response = await client.request(client.eventsUrl(name), {
    method: "POST",
    headers: client.requestHeaders({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(client.invocation(arguments_, options.target)),
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
          return event.answer;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  throw new AxonXError("Event stream ended without a terminal result");
}
