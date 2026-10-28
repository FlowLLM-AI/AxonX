import { useEffect } from "react";
import { listFullTaskStatuses } from "./features/tasks/api";

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
          name: "list_axonx_tasks",
          title: "List AxonX tasks",
          description:
            "Read the current runtime status of every Task managed by this AxonX service.",
          inputSchema: {
            type: "object",
            properties: {},
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute: async () => ({ tasks: await listFullTaskStatuses() }),
        },
        { signal: lifecycle.signal },
      ),
    ).catch(report);

    return () => lifecycle.abort();
  }, []);
}
