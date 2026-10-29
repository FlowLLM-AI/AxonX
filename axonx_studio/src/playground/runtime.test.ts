import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyAgentEvent,
  emptyConversation,
  fromHistory,
  optimisticUserBlock,
} from "../features/agent/reducer";
import { taskStepProgress } from "../features/tasks/model";
import { AxonXClient } from "../shared/api/client";
import type {
  AgentSession,
  AgentSessionInfo,
  TaskGraph,
  TaskMetadata,
  WorkspaceListing,
} from "../shared/api/contracts";
import type { WorkspacePreview } from "../shared/api/workspace";
import { upstreamTaskIds } from "../shared/lib/tasks";
import { createPlayground } from "./runtime";
import { taskCommand } from "../features/tasks/execution";
import { definitions } from "./data";
import { seed } from "./fixtures";
import { catalog } from "./catalog";
import contracts from "./job-contracts.json";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());
const client = () => new AxonXClient(createPlayground(), false);

describe("static Playground", () => {
  it.each(["success", "failure"])(
    "folds CLI events for ordinary API calls with %s outcome",
    async (outcome) => {
      const api = client();
      const command = api
        .invoke("cli", {
          argv: taskCommand(definitions[0].name, {
            task_name: "api-call",
            outcome,
          }),
        })
        .then(
          (result) => ({ result, error: null }),
          (error) => ({ result: null, error }),
        );
      await vi.advanceTimersByTimeAsync(2500);
      const result = await command;
      expect(Boolean(result.error)).toBe(outcome === "failure");
      const status = await api.invoke<TaskMetadata>("status", {
        task_id: "etl#playground_etl#api-call",
      });
      expect(status.reg_name).toBe(definitions[0].name);
      if (outcome === "success")
        expect(
          await api.invoke("stream_task", { task_id: status.task_id }),
        ).toEqual(status);
      else
        await expect(
          api.invoke("stream_task", { task_id: status.task_id }),
        ).rejects.toThrow();
      expect(vi.getTimerCount()).toBe(0);
    },
  );

  it("uses canonical identities and consistent invocation records throughout the virtual workspace", () => {
    const { tasks } = seed();
    for (const task of tasks.values()) {
      const parts = task.task_id.split("#");
      expect(parts).toHaveLength(3);
      expect(parts[0]).toBe(task.task_type);
      expect(parts[1]).toBe(task.reg_name);
      expect(parts[2]).toBe(task.input_params.task_name);
      expect(parts[2]).toMatch(/^[A-Za-z0-9-]{1,32}$/);
      expect(Date.parse(task.finished_at!)).toBeGreaterThanOrEqual(
        Date.parse(task.started_at),
      );
      for (const id of upstreamTaskIds(task.input_params.upstream_task_ids))
        expect(tasks.has(id)).toBe(true);
      for (const record of task.children) {
        const child = tasks.get(record.child_task_id!)!;
        expect(child).toBeDefined();
        expect(child.reg_name).toBe(record.reg_name);
        expect(child.started_at).toBe(record.started_at);
        expect(child.parent_task_id).toBe(task.task_id);
      }
    }
  });

  it("exposes current service schemas, version and lightweight Task discovery", async () => {
    const api = client();
    expect(
      catalog.items.find((job) => job.name === "preview_file")?.input_schema
        .required,
    ).toEqual(["path"]);
    expect(
      catalog.items.find((job) => job.name === "read_task_log")?.input_schema
        .properties,
    ).toHaveProperty("started_at");
    expect(
      await api.invoke("get_task_def", { task: definitions[0].name }),
    ).toEqual(definitions[0]);
    await expect(
      api.invoke("get_task_def", { task: "missing" }),
    ).rejects.toThrow("Unknown Task");
    const machine = await api.invoke<{ axonx: { version: string } }>(
      "machine_status",
    );
    expect(machine.axonx.version).toBe(contracts.version);
    const ids = await api.invoke<string[]>("list_task_ids");
    const summaries = await api.invoke<TaskMetadata[]>("list_task_statuses");
    expect(ids).toEqual(summaries.map((task) => task.task_id));
  });

  it.each(["success", "failure"])(
    "simulates a CLI Task with %s outcome and publishes a queryable record",
    async (outcome) => {
      const api = client();
      const definition = definitions[0];
      const name = `test-${outcome}`;
      const taskId = `${definition.task_type}#${definition.name}#${name}`;
      const logs: string[] = [];
      const command = api
        .stream(
          "cli",
          { argv: taskCommand(definition.name, { task_name: name, outcome }) },
          {
            onEvent: (event) => {
              if (event.kind === "log") logs.push(event.content);
            },
          },
        )
        .then(
          (result) => ({ result, error: null }),
          (error) => ({ result: null, error }),
        );
      await vi.advanceTimersByTimeAsync(2_500);
      const response = await command;
      const task = await api.invoke<TaskMetadata>("status", {
        task_id: taskId,
      });
      expect(task.state).toBe(outcome === "success" ? "succeeded" : "failed");
      expect(Boolean(response.error)).toBe(outcome === "failure");
      expect(logs.join("")).toContain("[simulation]");
      expect(task.input_params.task_name).toBe(name);
    },
  );

  it("stops a simulated command through the same CLI Job", async () => {
    const api = client();
    const definition = definitions[0];
    const taskId = `${definition.task_type}#${definition.name}#stop-test`;
    const command = api
      .stream("cli", {
        argv: taskCommand(definition.name, { task_name: "stop-test" }),
      })
      .catch((error) => error);
    await vi.advanceTimersByTimeAsync(200);
    await api.stream("cli", {
      argv: ["kill", "--task-id", JSON.stringify(taskId)],
    });
    await vi.advanceTimersByTimeAsync(500);
    await command;
    expect(
      (await api.invoke<TaskMetadata>("status", { task_id: taskId })).error,
    ).toBe("Simulation stopped");
  });
  it("defaults to summaries while preserving explicit full status and selected task details", async () => {
    const api = client();
    const full = await api.invoke<TaskMetadata[]>("list_task_statuses", {
      detail: "full",
    });
    const summaries =
      await api.invoke<import("../shared/api/contracts").TaskSummary[]>(
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
            path: `tasks/${task_type}`,
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
            input_params: { upstream_task_ids: string[] };
          };
          const task = await api.invoke<TaskMetadata>("status", {
            task_id: metadata.task_id,
          });
          if (task.state !== "succeeded") continue;
          expect(metadata.state).toBe("succeeded");
          const expectedSource: Record<string, string[]> = {
            analysis: ["etl#playground_etl#demo"],
            train: ["etl#playground_etl#demo"],
            predict: ["train#playground_train#demo"],
            backtest: ["predict#playground_predict#demo"],
          };
          if (
            metadata.task_id === `${task_type}#playground_${task_type}#demo` ||
            metadata.task_id === "backtest#playground_backtest#volatile"
          )
            expect(metadata.input_params.upstream_task_ids).toEqual(
              expectedSource[task_type] || [],
            );
          expect(task.input_params.upstream_task_ids).toEqual(
            metadata.input_params.upstream_task_ids,
          );
          if (task_type !== "etl")
            expect(
              upstreamTaskIds(metadata.input_params.upstream_task_ids),
            ).toHaveLength(1);
          for (const id of upstreamTaskIds(
            metadata.input_params.upstream_task_ids,
          ))
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
    const result = api.stream(
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
    const next = api.stream("agent_chat", {
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
    const result = api.stream(
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
    const resumed = api.stream("agent_chat", {
      session_id,
      message: "继续",
    });
    await vi.advanceTimersByTimeAsync(8000);
    await resumed;
    expect(vi.getTimerCount()).toBe(0);
  });
});
