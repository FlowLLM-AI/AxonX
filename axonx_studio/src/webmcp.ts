import { useEffect } from "react";
import { listTaskStatuses, submitTask } from "./features/tasks/api";

interface ModelContext {
  registerTool(
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
      execute(input: unknown): unknown | Promise<unknown>;
    },
    options?: { signal?: AbortSignal },
  ): void | Promise<void>;
}

declare global {
  interface Document {
    readonly modelContext?: ModelContext;
  }
}

export function useAxonXWebMcp() {
  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const report = (error: unknown) =>
      console.warn("Unable to register AxonX browser tool", error);

    void Promise.resolve(
      context.registerTool(
        {
          name: "list_axonx_task_runs",
          title: "List AxonX task runs",
          description:
            "Read the current runtime status of every Task managed by this AxonX service.",
          inputSchema: {
            type: "object",
            properties: {},
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute: async () => ({ tasks: await listTaskStatuses() }),
        },
        { signal: lifecycle.signal },
      ),
    ).catch(report);

    void Promise.resolve(
      context.registerTool(
        {
          name: "submit_axonx_task",
          title: "Submit an AxonX Task",
          description:
            "Submit one installed Task with its validated configuration to the AxonX worker manager.",
          inputSchema: {
            type: "object",
            properties: {
              task: { type: "string" },
              config: { type: "object" },
            },
            required: ["task", "config"],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute: async (input) => {
            if (!input || typeof input !== "object")
              throw new Error("Expected a task and config object");
            const { task, config } = input as {
              task?: unknown;
              config?: unknown;
            };
            if (
              typeof task !== "string" ||
              !task ||
              !config ||
              typeof config !== "object" ||
              Array.isArray(config)
            ) {
              throw new Error(
                "Expected a non-empty task name and config object",
              );
            }
            return submitTask(task, config as Record<string, unknown>);
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(report);

    return () => lifecycle.abort();
  }, []);
}
