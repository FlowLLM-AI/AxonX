import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyAgentEvent,
  emptyConversation,
  fromHistory,
  optimisticUserBlock,
} from "../features/agent/reducer";
import type { AgentSession, AgentSessionInfo } from "../features/agent/types";
import type { TaskGraph } from "../features/task-graph/types";
import { taskStepProgress } from "../features/tasks/format";
import type { TaskMetadata } from "../features/tasks/types";
import type {
  WorkspaceListing,
  WorkspacePreview,
} from "../features/workspace/types";
import { AxonXClient } from "../shared/api/client";
import { streamJob } from "../shared/api/event";
import { parseSourceTasks } from "../shared/lib/sourceTasks";
import { createPlayground } from "./runtime";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const client = () => new AxonXClient(createPlayground(), false);

describe("static Playground", () => {
  it("defaults to summaries while preserving explicit full status and selected task details", async () => {
    const api = client();
    const full = await api.invoke<TaskMetadata[]>("list_task_statuses", {
      detail: "full",
    });
    const summaries =
      await api.invoke<import("../features/tasks/types").TaskSummary[]>(
        "list_task_statuses",
      );
    expect(summaries.map((task) => task.task_id)).toEqual(
      full.map((task) => task.task_id),
    );
    for (const summary of summaries) {
      expect(summary).not.toHaveProperty("input_params");
      expect(summary).not.toHaveProperty("output_params");
      expect(summary).not.toHaveProperty("steps");
      const detail = await api.invoke<TaskMetadata>("status", {
        task_id: summary.task_id,
      });
      expect(detail).toHaveProperty("output_params");
      const compact = await api.invoke("status", {
        task_id: summary.task_id,
        detail: "summary",
      });
      expect(compact).toEqual(summary);
      await expect(
        api.invoke("read_task_log", {
          task_id: summary.task_id,
          started_at: "2026-01-02T00:00:00Z",
        }),
      ).rejects.toThrow("Task restarted");
      expect(summary.step_progress?.current ?? null).toBe(
        taskStepProgress(detail)?.current ?? null,
      );
      const graph = await api.invoke<TaskGraph>("get_task_graph", {
        task_id: summary.task_id,
      });
      const selected = graph.nodes.find(
        (node) => node.task_id === summary.task_id,
      );
      expect(selected?.provisional).toBe(detail.state !== "succeeded");
    }
  });
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
        const runs = await api.invoke<WorkspaceListing>(
          "list_task_directories",
          {
            task_type,
          },
        );
        expect(runs.entries.length).toBeGreaterThan(0);
        for (const run of runs.entries) {
          const preview = await api.invoke<WorkspacePreview>("preview_file", {
            path: `${run.path}/metadata.json`,
          });
          expect(preview.kind).toBe("json");
          if (preview.kind !== "json") throw new Error("Missing metadata");
          const metadata = preview.data as {
            task_id: string;
            state: string;
            output_params: {
              artifacts: Record<string, { path: string }>;
              protocol?: Record<string, unknown>;
            };
            input_params: { source_tasks: string };
          };
          const task = await api.invoke<TaskMetadata>("status", {
            task_id: metadata.task_id,
          });
          if (task.state !== "succeeded") continue;
          expect(metadata.state).toBe("succeeded");
          const expectedSource: Record<string, string> = {
            analysis: "etl#demo",
            train: "etl#demo",
            predict: "train#demo",
            backtest: "predict#demo",
          };
          if (
            metadata.task_id === `${task_type}#demo` ||
            metadata.task_id === "backtest#volatile"
          )
            expect(metadata.input_params.source_tasks).toBe(
              expectedSource[task_type] || "",
            );
          expect(task.input_params.source_tasks).toBe(
            metadata.input_params.source_tasks,
          );
          if (task_type !== "etl")
            expect(
              parseSourceTasks(metadata.input_params.source_tasks),
            ).toHaveLength(1);
          for (const id of parseSourceTasks(metadata.input_params.source_tasks))
            await api.invoke("status", { task_id: id });
          expect(metadata.output_params).not.toHaveProperty("output_file");
          expect(metadata.output_params).not.toHaveProperty("result_file");
          expect(metadata.output_params).not.toHaveProperty("model_files");
          expect(metadata.output_params).not.toHaveProperty("predictions_file");
          if (task_type === "train")
            expect(
              metadata.output_params.artifacts.model_manifest,
            ).toBeDefined();
          if (task_type === "predict")
            expect(
              (metadata.output_params.protocol as { score_columns: object })
                .score_columns,
            ).toEqual({ model: "pred" });
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
