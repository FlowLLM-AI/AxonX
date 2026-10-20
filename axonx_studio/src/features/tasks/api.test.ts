import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, configureClient } from "../../shared/api/client";
import { listFullTaskStatuses, listTaskStatuses } from "./api";

afterEach(() => configureClient(new AxonXClient()));

describe("task list requests", () => {
  it("uses summaries for Studio and preserves full snapshots for browser tools", async () => {
    const transport = vi
      .fn()
      .mockImplementation(async () =>
        Response.json({ success: true, answer: [] }),
      );
    configureClient(new AxonXClient(transport, false));
    const signal = new AbortController().signal;
    await listTaskStatuses("remote:1024", signal);
    await listFullTaskStatuses("remote:1024", signal);
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

it("explicitly requests bounded schedule history for operation pages", async () => {
  const transport = vi.fn(async () =>
    Response.json({ success: true, answer: [] }),
  );
  configureClient(new AxonXClient(transport, false));
  const { listSchedules } = await import("./api");
  const signal = new AbortController().signal;
  await listSchedules("remote:1024", signal, "daily");
  const [url, init] = transport.mock.calls[0] as unknown as [
    string,
    RequestInit,
  ];
  expect(url).toBe("/jobs/list_schedules");
  expect(init.signal).toBe(signal);
  expect(JSON.parse(init.body as string)).toEqual({
    target: "remote:1024",
    arguments: { name: "daily", include_history: true, history_limit: 200 },
  });
});
