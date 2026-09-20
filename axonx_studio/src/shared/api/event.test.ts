import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient } from "./client";
import { streamJob } from "./event";

afterEach(() => vi.unstubAllGlobals());

describe("streamJob", () => {
  it("decodes split SSE frames and returns the terminal result", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: progress\ndata: {"kind":"progress","name":"run","started_at":null,',
          ),
        );
        controller.enqueue(
          encoder.encode(
            '"finished_at":null,"percentage":50}\n\nevent: result\ndata: {"kind":"result","answer":{"done":true},"success":true,"metadata":{}}\n\n',
          ),
        );
        controller.close();
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );
    const events: string[] = [];
    const result = await streamJob<{ done: boolean }>(
      new AxonXClient("http://axonx.test"),
      "stream_task",
      { task_id: "task" },
      { onEvent: (event) => events.push(event.kind) },
    );
    expect(result).toEqual({ done: true });
    expect(events).toEqual(["progress", "result"]);
  });
});
