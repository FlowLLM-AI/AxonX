import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import {
  executeTaskCommand,
  listFullTaskStatuses,
  listTaskStatuses,
} from "./api";

afterEach(() => configureClient(new AxonXClient()));

describe("task list requests", () => {
  it("executes through CLI SSE and binds the selected target to the request", async () => {
    const transport = vi.fn(
      async () =>
        new Response(
          'data: {"kind":"result","success":true,"answer":{"stdout":"5","stderr":"","exit_code":0},"metadata":{}}\n\n',
          { headers: { "Content-Type": "text/event-stream" } },
        ),
    );
    configureClient(new AxonXClient(transport, false));
    const argv = ["exec", "--task", '"demo"', "--x", "2", "--y", "3"];
    const signal = new AbortController().signal;
    const answer = await executeTaskCommand(argv, {
      target: "remote:1024",
      signal,
    });
    const [url, init] = transport.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/jobs/cli/events");
    expect(init.signal).toBe(signal);
    expect(JSON.parse(String(init.body))).toEqual({
      target: "remote:1024",
      arguments: { argv },
    });
    expect(answer.exit_code).toBe(0);
  });
  it("uses summaries for Studio and preserves full snapshots for browser tools", async () => {
    const transport = vi
      .fn()
      .mockImplementation(async () =>
        Response.json({ success: true, answer: [] }),
      );
    configureClient(new AxonXClient(transport, false));
    const signal = new AbortController().signal;
    await listTaskStatuses({ target: "remote:1024", signal });
    await listFullTaskStatuses({ target: "remote:1024", signal });
    for (const [index, detail] of ["summary", "full"].entries()) {
      const [url, init] = transport.mock.calls[index];
      expect(url).toBe("/jobs/list_task_statuses");
      expect(init.signal).toBe(signal);
      expect(JSON.parse(init.body)).toEqual({
        target: "remote:1024",
        arguments: { detail },
      });
    }
  });
});
