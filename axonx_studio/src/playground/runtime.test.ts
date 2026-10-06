import { parseSourceTasks } from "../shared/lib/sourceTasks";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AxonXClient } from "../shared/api/client";
import { streamJob } from "../shared/api/event";
import { createPlayground } from "./runtime";
import type { TaskHandle, TaskStatus } from "../features/tasks/types";
import type {
  WorkspaceDirectory,
  WorkspacePreview,
} from "../features/workspace/types";
import type { AgentSession, AgentSessionInfo } from "../features/agent/types";
import {
  fromHistory,
  applyAgentEvent,
  emptyConversation,
  optimisticUserBlock,
} from "../features/agent/reducer";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const client = () => new AxonXClient(createPlayground(), false);
const submit = (api: AxonXClient, extra = {}) =>
  api.invoke<TaskHandle>("submit", { task: "playground.backtest", ...extra });

describe("static Playground", () => {
  it("loads every research run and all declared artifacts without network or credentials", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("Network forbidden"));
    try {
      const api = client();
      api.setToken("secret");
      expect(api.requestHeaders().has("Authorization")).toBe(false);
      expect(api.hasToken()).toBe(false);
      for (const task_type of [
        "etl",
        "analysis",
        "train",
        "predict",
        "backtest",
      ]) {
        const runs = await api.invoke<WorkspaceDirectory>("list_task_runs", {
          task_type,
        });
        expect(runs.entries.length).toBeGreaterThan(0);
        for (const run of runs.entries) {
          const preview = await api.invoke<WorkspacePreview>("preview_file", {
            path: `${run.path}/metadata.json`,
          });
          expect(preview.kind).toBe("json");
          if (preview.kind !== "json") throw new Error("Missing metadata");
          const metadata = preview.data as {
            task_id: string;
            output_params: {
              artifacts: Record<string, { path: string }>;
              output_file?: string;
              result_file?: string;
              model_file?: string;
              predictions_file?: string;
            };
            input_params: { source_tasks: string };
          };
          const task = await api.invoke<TaskStatus>("status", {
            task_id: metadata.task_id,
          });
          expect(task.state).toBe("succeeded");
          if (task_type !== "etl")
            expect(
              parseSourceTasks(metadata.input_params.source_tasks),
            ).toHaveLength(1);
          for (const id of parseSourceTasks(metadata.input_params.source_tasks))
            await api.invoke("status", { task_id: id });
          for (const key of [
            "output_file",
            "result_file",
            "model_file",
            "predictions_file",
          ] as const) {
            const path = metadata.output_params[key];
            if (path) await api.invoke("preview_file", { path });
          }
          for (const artifact of Object.values(
            metadata.output_params.artifacts,
          )) {
            const data = await api.invoke<WorkspacePreview>("preview_file", {
              path: `${run.path}/${artifact.path}`,
            });
            expect(["parquet", "json"]).toContain(data.kind);
          }
        }
      }
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      fetch.mockRestore();
    }
  });

  it("keeps return summaries and graph lineage consistent with rendered data", async () => {
    const api = client();
    const daily = await api.invoke<WorkspacePreview>("preview_file", {
      path: "runs/backtest#demo/daily.parquet",
      limit: 100,
    });
    const summary = await api.invoke<WorkspacePreview>("preview_file", {
      path: "runs/backtest#demo/summary.parquet",
      limit: 100,
    });
    if (daily.kind !== "parquet" || summary.kind !== "parquet")
      throw new Error("Missing backtest tables");
    const net = daily.columns.indexOf("top5_net_return");
    const cumulative =
      daily.rows.reduce(
        (equity: number, row) => equity * (1 + Number(row[net])),
        1,
      ) - 1;
    const overall = summary.rows.find(
      (row) => row[summary.columns.indexOf("period_type")] === "overall",
    )!;
    expect(
      overall[summary.columns.indexOf("top5_net_cumulative_return")],
    ).toBeCloseTo(cumulative, 12);
    const graph = await api.invoke<{
      nodes: { task_id: string; missing: boolean }[];
      edges: { from: string; to: string }[];
    }>("get_task_graph", { task_id: "backtest#demo" });
    expect(graph.nodes).toHaveLength(6);
    expect(graph.edges).toContainEqual({
      from: "predict#demo",
      to: "backtest#volatile",
    });
    await api.invoke("delete_tasks", { task_ids: ["train#demo"] });
    const missing = await api.invoke<typeof graph>("get_task_graph", {
      task_id: "backtest#demo",
    });
    expect(
      missing.nodes.find((node) => node.task_id === "train#demo")?.missing,
    ).toBe(true);
  });

  it("paginates rows and rejects unknown jobs, files and targets", async () => {
    const api = client();
    const page = await api.invoke<WorkspacePreview>("preview_file", {
      path: "tushare/daily/sample.parquet",
      offset: 1795,
      limit: 10,
    });
    expect(page.kind).toBe("parquet");
    if (page.kind !== "parquet") throw new Error("Expected table");
    expect(page.rows).toHaveLength(5);
    expect(page.has_more).toBe(false);
    await expect(api.invoke("unknown")).rejects.toThrow(
      "Unsupported Playground Job",
    );
    await expect(
      api.invoke("preview_file", { path: "private" }),
    ).rejects.toThrow("not found");
    await expect(
      api.invoke("status", {}, { target: "remote" }),
    ).rejects.toThrow("demo browser");
  });

  it("advances tasks without subscribers, writes artifacts, and isolates each browser runtime", async () => {
    const api = client();
    const handle = await submit(api, { strategy: "volatile" });
    const status = () => api.invoke<TaskStatus>("status", { ...handle });
    expect((await status()).state).toBe("queued");
    await vi.advanceTimersByTimeAsync(2000);
    expect((await status()).state).toBe("running");
    await vi.advanceTimersByTimeAsync(5000);
    expect((await status()).state).toBe("succeeded");
    await api.invoke("preview_file", {
      path: `runs/${handle.task_id}/daily.parquet`,
    });
    await expect(client().invoke("status", { ...handle })).rejects.toThrow(
      "Unknown demo task",
    );
    await api.invoke("delete_tasks", { task_ids: [handle.task_id] });
    await expect(status()).rejects.toThrow("Unknown demo task");
    await expect(
      api.invoke("preview_file", {
        path: `runs/${handle.task_id}/metadata.json`,
      }),
    ).rejects.toThrow("not found");
  });

  it("cancels tasks permanently and models failures without success artifacts", async () => {
    const api = client();
    const cancelled = await submit(api);
    expect(
      await api.invoke("cancel", { ...cancelled, run_id: "stale-run" }),
    ).toBe(false);
    expect(
      (await api.invoke<TaskStatus>("status", { ...cancelled })).state,
    ).toBe("queued");
    expect(await api.invoke("cancel", { run_id: cancelled.run_id })).toBe(true);
    const failed = await submit(api, { outcome: "failure" });
    await vi.advanceTimersByTimeAsync(7000);
    expect(
      (await api.invoke<TaskStatus>("status", { ...cancelled })).state,
    ).toBe("cancelled");
    expect((await api.invoke<TaskStatus>("status", { ...failed })).state).toBe(
      "failed",
    );
    await expect(
      api.invoke("preview_file", {
        path: `runs/${failed.task_id}/metadata.json`,
      }),
    ).rejects.toThrow("not found");
  });

  it("cancels a current task by Task ID and rejects an empty cancellation", async () => {
    const api = client();
    const handle = await submit(api);
    await expect(api.invoke("cancel", {})).rejects.toThrow(
      "Cancellation requires task_id or run_id",
    );
    expect(await api.invoke("cancel", { run_id: "unknown-run" })).toBe(false);
    expect(await api.invoke("cancel", { task_id: handle.task_id })).toBe(true);
    expect(await api.invoke("cancel", { task_id: handle.task_id })).toBe(false);
    expect(
      (await api.invoke<TaskStatus>("status", { task_id: handle.task_id }))
        .state,
    ).toBe("cancelled");
  });

  it("streams progress through the real SSE parser and cleans up timers", async () => {
    const api = client();
    const handle = await submit(api);
    const kinds: string[] = [];
    const result = streamJob<TaskStatus>(
      api,
      "stream_task",
      { ...handle },
      {
        onEvent: (event) => kinds.push(event.kind),
      },
    );
    await vi.advanceTimersByTimeAsync(7000);
    expect((await result).state).toBe("succeeded");
    expect(kinds).toContain("progress");
    expect(kinds).toContain("log");
    expect(kinds).toContain("artifact");
    expect(kinds.at(-1)).toBe("result");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("aborts a subscription without cancelling its task", async () => {
    const api = client();
    const handle = await submit(api);
    const controller = new AbortController();
    const result = streamJob(
      api,
      "stream_task",
      { ...handle },
      {
        signal: controller.signal,
      },
    );
    const rejected = expect(result).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.advanceTimersByTimeAsync(500);
    controller.abort();
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(7000);
    expect((await api.invoke<TaskStatus>("status", { ...handle })).state).toBe(
      "succeeded",
    );
  });

  it("streams Agent history consistently and supports turn cancellation", async () => {
    const api = client();
    const started = Date.now();
    let conversation = optimisticUserBlock(
      emptyConversation(),
      "解释回测",
      "local-prompt",
    );
    let session_id = "";
    const result = streamJob(
      api,
      "agent_chat",
      { message: "解释回测" },
      {
        onEvent: (event) => {
          if (event.kind === "agent_message") {
            session_id = event.session_id;
            conversation = applyAgentEvent(conversation, event);
          }
        },
      },
    );
    await vi.advanceTimersByTimeAsync(8000);
    await result;
    const history = await api.invoke<AgentSession>("get_agent_session", {
      session_id,
    });
    expect(history.info.last_modified).toBeGreaterThanOrEqual(started);
    expect(history.info.last_modified).toBeLessThanOrEqual(Date.now());
    expect(
      conversation.order.filter(
        (id) => conversation.blocks[id].role === "user",
      ),
    ).toHaveLength(1);
    expect(
      fromHistory(
        conversation.order
          .filter((id) => id !== "local-prompt")
          .map((id) => conversation.blocks[id]),
      ),
    ).toEqual(
      fromHistory(history.blocks.filter((block) => block.role === "assistant")),
    );
    expect(history.blocks[0].role).toBe("user");
    expect(history.blocks[1].block_type).toBe("tool");
    expect(history.blocks[2].text).toContain("没有调用 LLM");
    const next = streamJob(api, "agent_chat", {
      session_id,
      message: "Compare",
    });
    await vi.advanceTimersByTimeAsync(500);
    await api.invoke("cancel_agent_turn", { session_id });
    await vi.advanceTimersByTimeAsync(500);
    await next;
    expect(vi.getTimerCount()).toBe(0);
    await api.invoke("delete_agent_session", { session_id });
    const sessions = await api.invoke<AgentSessionInfo[]>(
      "list_agent_sessions",
    );
    expect(sessions.some((session) => session.session_id === session_id)).toBe(
      false,
    );
  });
  it("closes aborted Agent turns and allows resuming the session", async () => {
    const api = client();
    const controller = new AbortController();
    let session_id = "";
    const result = streamJob(
      api,
      "agent_chat",
      { message: "Compare" },
      {
        signal: controller.signal,
        onEvent: (event) => {
          if (event.kind === "agent_message") session_id = event.session_id;
        },
      },
    );
    const rejected = expect(result).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.advanceTimersByTimeAsync(500);
    controller.abort();
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    const history = await api.invoke<AgentSession>("get_agent_session", {
      session_id,
    });
    expect(history.blocks.every((block) => block.status !== "running")).toBe(
      true,
    );
    const resumed = streamJob(api, "agent_chat", {
      session_id,
      message: "继续",
    });
    await vi.advanceTimersByTimeAsync(8000);
    await resumed;
    expect(vi.getTimerCount()).toBe(0);
  });
});
