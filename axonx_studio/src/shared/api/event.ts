import type { RequestOptions } from "./client";
import type {
  AgentMessageEvent,
  ArtifactEvent,
  LogEvent,
  ProgressEvent,
  TaskStepStatus as StepContract,
} from "./contracts";
import { AxonXError, jobAnswer, readJobResponse } from "./response";
import type { JobResponse } from "./types";

export type {
  AgentBlockPatch,
  AgentMessageEvent,
  ArtifactEvent,
  LogEvent,
  ProgressEvent,
} from "./contracts";

/** Presentation also accepts partial live progress snapshots. */
export type TaskStepStatus = Pick<
  StepContract,
  "name" | "started_at" | "finished_at" | "percentage"
> &
  Partial<StepContract>;

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
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
}

export async function readJobEvents<T>(
  response: Response,
  onEvent?: StreamOptions<T>["onEvent"],
): Promise<T> {
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
        onEvent?.(event);
        if (event.kind === "result") {
          return jobAnswer<T>(event, response.status);
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  throw new AxonXError("Event stream ended without a terminal result");
}
