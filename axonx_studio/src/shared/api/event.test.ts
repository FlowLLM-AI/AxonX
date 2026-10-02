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
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: string[] = [];
    const result = await streamJob<{ done: boolean }>(
      new AxonXClient(),
      "stream_task",
      { task_id: "task" },
      {
        target: "http://remote.test:1024",
        onEvent: (event) => events.push(event.kind),
      },
    );
    expect(result).toEqual({ done: true });
    expect(events).toEqual(["progress", "result"]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/jobs/stream_task/events");
    expect(JSON.parse(String(init.body))).toEqual({
      arguments: { task_id: "task" },
      target: "http://remote.test:1024",
    });
  });
});
