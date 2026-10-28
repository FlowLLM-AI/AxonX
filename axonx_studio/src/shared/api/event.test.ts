import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient } from "./client";
import { AxonXError } from "./response";

afterEach(() => vi.unstubAllGlobals());

describe("AxonXClient.stream", () => {
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
    const client = new AxonXClient();
    client.setToken("stream-secret");
    const signal = new AbortController().signal;
    const events: string[] = [];
    const result = await client.stream<{ done: boolean }>(
      "stream_task",
      { task_id: "task" },
      {
        target: "http://remote.test:1024",
        signal,
        onEvent: (event) => events.push(event.kind),
      },
    );
    expect(result).toEqual({ done: true });
    expect(events).toEqual(["progress", "result"]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/jobs/stream_task/events");
    expect(init.signal).toBe(signal);
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer stream-secret",
    );
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
    expect(JSON.parse(String(init.body))).toEqual({
      arguments: { task_id: "task" },
      target: "http://remote.test:1024",
    });
    client.setToken("");
  });

  it.each([{ success: "false", answer: 42 }, { success: true }])(
    "rejects malformed terminal results: %j",
    async (payload) => {
      const client = new AxonXClient(
        async () =>
          new Response(
            `data:${JSON.stringify({ kind: "result", ...payload })}\n\n`,
            { headers: { "Content-Type": "text/event-stream" } },
          ),
        false,
      );
      await expect(client.stream("demo")).rejects.toEqual(
        new AxonXError("Invalid AxonX response envelope", 200),
      );
    },
  );

  it("delivers failed terminal events and closes their reader", async () => {
    const cancel = vi.fn();
    const event = {
      kind: "result",
      success: false,
      answer: "Failed",
      metadata: { terminal_reason: "failed" },
    };
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(`data:${JSON.stringify(event)}\n\n`),
        );
      },
      cancel,
    });
    const client = new AxonXClient(
      async () =>
        new Response(body, {
          headers: { "Content-Type": "text/event-stream" },
        }),
      false,
    );
    const onEvent = vi.fn();
    await expect(client.stream("demo", {}, { onEvent })).rejects.toEqual(
      new AxonXError("Failed", 200),
    );
    expect(onEvent).toHaveBeenCalledWith(event);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("reports HTTP failures before parsing the stream", async () => {
    const client = new AxonXClient(
      async () => Response.json({ detail: "Unknown job" }, { status: 404 }),
      false,
    );
    await expect(client.stream("missing")).rejects.toEqual(
      new AxonXError("Unknown job", 404),
    );
  });

  it("rejects a stream that ends without a terminal result", async () => {
    const client = new AxonXClient(
      async () =>
        new Response("", {
          headers: { "Content-Type": "text/event-stream" },
        }),
      false,
    );
    await expect(client.stream("demo")).rejects.toThrow(
      "without a terminal result",
    );
  });
});
