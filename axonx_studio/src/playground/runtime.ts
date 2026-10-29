import { taskStepProgress } from "../features/tasks/model";
import type { Transport } from "../shared/api/client";
import type {
  TaskMetadata,
  TaskSummary,
  WorkspaceListing,
} from "../shared/api/contracts";
import { readJobEvents, type JobEvent } from "../shared/api/event";
import { taskDirectory, upstreamTaskIds } from "../shared/lib/tasks";
import { createAgent } from "./agent";
import { catalog } from "./catalog";
import { addArtifacts, definitions, epoch, json, taskStatus } from "./data";
import { seed } from "./fixtures";
import { sse } from "./stream";
import contracts from "./job-contracts.json";

const envelope = (answer: unknown, success = true, metadata = {}) => ({
  answer,
  success,
  metadata,
});
const response = (answer: unknown, success = true) =>
  Response.json(envelope(answer, success));
const abortError = () => new DOMException("Aborted", "AbortError");
const terminal = (answer: unknown, metadata = {}): JobEvent => ({
  kind: "result",
  ...envelope(answer, true, metadata),
});

function taskView(
  task: TaskMetadata,
  detail: unknown = "full",
): TaskMetadata | TaskSummary {
  if (detail === "full") return task;
  if (detail !== "summary") throw new Error("detail must be summary or full");
  const {
    input_params,
    output_params,
    steps,
    children,
    replica,
    version,
    ...summary
  } = task;
  void output_params;
  void children;
  void version;
  const roots = steps.filter((step) => !step.parent);
  const progress = taskStepProgress(task);
  const step = progress ? roots[progress.current - 1] : undefined;
  return {
    ...summary,
    error: task.error.slice(0, 1000),
    display_name: String(input_params.task_name || task.reg_name).slice(0, 256),
    is_replica: replica !== null,
    step_progress: progress
      ? {
          ...progress,
          total: roots.length,
          name: step!.name.slice(0, 256),
          percentage: step!.percentage,
        }
      : null,
  };
}

export function createPlayground(): Transport {
  const { tasks, files, sourceFiles } = seed();
  const agent = createAgent();
  const requiredTask = (id: string) => {
    const task = tasks.get(id);
    if (!task) throw new Error(`KeyError: '${id}'`);
    return task;
  };
  const log = (id: string) => {
    const task = requiredTask(id);
    return (
      [
        `[demo] ${task.reg_name}`,
        ...task.steps
          .filter((step) => step.started_at)
          .map(
            (step) =>
              `[demo] ${step.name}: ${Math.round(step.percentage || 0)}%`,
          ),
        `[demo] ${task.state}${task.error ? `: ${task.error}` : ""}`,
      ].join("\n") + "\n"
    );
  };
  const logChunk = (id: string, offset = 0, limit = 65536) => {
    const content = new TextEncoder().encode(log(id));
    const start =
      offset < 0
        ? Math.max(0, content.length - limit)
        : Math.min(offset, content.length);
    return {
      content: new TextDecoder().decode(content.slice(start, start + limit)),
      start_offset: start,
      next_offset: Math.min(content.length, start + limit),
      file_size: content.length,
      has_more_before: start > 0,
      has_more_after: start + limit < content.length,
      reset: offset > content.length,
      channel: "stdout",
    };
  };
  function directory(path: string, offset = 0): WorkspaceListing {
    const prefix = path ? `${path}/` : "";
    const entries = new Map<string, WorkspaceListing["entries"][number]>();
    for (const [file, preview] of files) {
      if (!file.startsWith(prefix)) continue;
      const remainder = file.slice(prefix.length);
      const name = remainder.split("/")[0];
      const folder = remainder.includes("/");
      entries.set(name, {
        name,
        path: `${prefix}${name}`,
        kind: folder ? "directory" : "file",
        preview_kind: folder ? null : preview.kind,
        supported: true,
        size: folder ? null : preview.size,
        modified_at: Date.parse(epoch) / 1000,
      });
    }
    const sorted = [...entries.values()].sort(
      (a, b) =>
        Number(b.kind === "directory") - Number(a.kind === "directory") ||
        a.name.toLowerCase().localeCompare(b.name.toLowerCase()) ||
        a.name.localeCompare(b.name),
    );
    return {
      path,
      workspace_root: "/demo/workspace",
      entries: sorted.slice(offset, offset + 5000),
      truncated: sorted.length > offset + 5000,
    };
  }
  const transport: Transport = async (url, init = {}) => {
    if (init.signal?.aborted) throw abortError();
    const parsed = new URL(url, "https://playground.invalid");
    const name = decodeURIComponent(parsed.pathname.split("/")[2] || "");
    const invocation = init.body ? JSON.parse(String(init.body)) : {};
    const args: Record<string, unknown> = invocation.arguments || {};
    const target = invocation.target || parsed.searchParams.get("target");
    const id = String(args.task_id || "");
    try {
      if (target)
        throw new Error(
          "Playground only supports the demo browser / 演示仅支持浏览器环境",
        );
      if (parsed.pathname.endsWith("/events")) {
        if (name === "cli") {
          const argv = args.argv;
          if (
            !Array.isArray(argv) ||
            argv.some((value) => typeof value !== "string")
          )
            throw new Error("Expected CLI argv strings");
          const inputs: Record<string, unknown> = {};
          for (let at = 1; at < argv.length; at += 2) {
            const key = argv[at].replace(/^--/, "").replaceAll("-", "_");
            try {
              inputs[key] = JSON.parse(argv[at + 1]);
            } catch {
              inputs[key] = argv[at + 1];
            }
          }
          if (argv[0] === "kill") {
            const task = requiredTask(String(inputs.task_id));
            task.state = "failed";
            task.error = "Simulation stopped";
            task.exit_code = 1;
            task.finished_at = new Date().toISOString();
            return sse(
              () => [
                terminal({
                  stdout: "",
                  stderr: "",
                  exit_code: 0,
                  stdout_truncated: false,
                  stderr_truncated: false,
                }),
              ],
              init.signal,
            );
          }
          const definition = definitions.find(
            (task) => task.name === inputs.task,
          );
          if (argv[0] !== "exec" || !definition)
            throw new Error("Unknown simulated Task");
          const taskName =
            inputs.task_name ??
            `${new Date().toISOString().replace(/\D/g, "").slice(0, 10)}${crypto.randomUUID().slice(0, 4)}`;
          if (
            typeof taskName !== "string" ||
            !/^[A-Za-z0-9-]{1,32}$/.test(taskName)
          )
            throw new Error(
              "task_name must contain 1-32 letters, digits, or hyphens",
            );
          inputs.task_name = taskName;
          const taskId = `${definition.task_type}#${definition.name}#${taskName}`;
          const previous = tasks.get(taskId);
          if (previous?.state === "running") throw new Error("Task is running");
          const task = taskStatus(definition.task_type, taskId);
          const { task: registration, ...parameters } = inputs;
          void registration;
          task.input_params = { upstream_task_ids: [], ...parameters };
          task.state = "running";
          task.created_at = task.started_at = new Date(
            Math.max(
              Date.now(),
              previous ? Date.parse(previous.started_at) + 1 : 0,
            ),
          ).toISOString();
          task.finished_at = null;
          task.exit_code = 0;
          for (const step of task.steps) {
            step.state = "pending";
            step.percentage = 0;
            step.started_at = step.finished_at = null;
          }
          tasks.set(taskId, task);
          let tick = 0;
          const publish = () =>
            files.set(`${taskDirectory(taskId)}/metadata.json`, json(task));
          publish();
          return sse(
            () => {
              tick++;
              if (task.state === "running") {
                for (const [index, step] of task.steps.entries()) {
                  step.percentage = Math.max(
                    0,
                    Math.min(100, (tick - index * 2) * 50),
                  );
                  step.state =
                    step.percentage >= 100
                      ? "done"
                      : step.percentage
                        ? "running"
                        : "pending";
                  if (step.percentage && !step.started_at)
                    step.started_at = new Date().toISOString();
                  if (step.state === "done")
                    step.finished_at = new Date().toISOString();
                }
                if (tick >= 6) {
                  task.state =
                    inputs.outcome === "failure" ? "failed" : "succeeded";
                  task.exit_code = task.state === "succeeded" ? 0 : 1;
                  task.finished_at = new Date().toISOString();
                  task.error =
                    task.state === "failed" ? "Simulated Task failure" : "";
                  if (task.state === "succeeded") {
                    const parameters = task.input_params;
                    addArtifacts(
                      files,
                      task,
                      String(inputs.strategy || "steady"),
                      parameters.upstream_task_ids as string[],
                    );
                    task.input_params = { ...task.input_params, ...parameters };
                  }
                }
              }
              publish();
              const events: JobEvent[] = [
                {
                  kind: "log",
                  ...logChunk(taskId),
                  content: `[simulation] ${definition.name}: ${task.state} (${Math.min(100, Math.round((tick / 6) * 100))}%)\n`,
                },
              ];
              if (task.state !== "running")
                events.push({
                  kind: "result",
                  ...envelope(
                    {
                      stdout: JSON.stringify(task.output_params),
                      stderr: task.error,
                      exit_code: task.exit_code,
                      stdout_truncated: false,
                      stderr_truncated: false,
                    },
                    task.state === "succeeded",
                  ),
                });
              return events;
            },
            init.signal,
            () => {
              if (task.state === "running") {
                task.state = "failed";
                task.error = "Simulation connection closed";
                task.exit_code = 1;
                task.finished_at = new Date().toISOString();
                publish();
              }
            },
          );
        }
        if (name === "stream_task") {
          requiredTask(id);
          return sse(() => {
            const task = requiredTask(id);
            const events: JobEvent[] = [
              ...task.steps.map((step) => ({
                kind: "progress" as const,
                ...step,
              })),
              { kind: "log", ...logChunk(id), reset: true },
            ];
            {
              for (const [path, file] of files)
                if (path.startsWith(`${taskDirectory(id)}/`))
                  events.push({
                    kind: "artifact",
                    path,
                    size: file.size,
                    sha256: "",
                    media_type:
                      file.kind === "json" ? "application/json" : null,
                    extra: { simulated: true },
                  });
              if (task.state !== "running")
                events.push({
                  kind: "result",
                  ...envelope(task, task.state === "succeeded"),
                });
            }
            return events;
          }, init.signal);
        }
        if (name === "agent_chat") return agent.stream(args, init.signal);
        throw new Error(`Unsupported demo stream: ${name}`);
      }
      if (parsed.pathname === "/jobs") return response(catalog);
      if (["cli", "stream_task", "agent_chat"].includes(name)) {
        const stream = await transport(`/jobs/${name}/events`, init);
        let result: ReturnType<typeof envelope> | undefined;
        try {
          await readJobEvents(stream, (event) => {
            if (event.kind === "result")
              result = envelope(event.answer, event.success, event.metadata);
          });
        } catch (error) {
          if (!result) throw error;
        }
        return Response.json(result);
      }
      if (Object.hasOwn(agent.jobs, name))
        return response(agent.jobs[name](args));
      switch (name) {
        case "python": {
          const code = String(args.code || "");
          const settings = code.match(/^settings = json.loads\((.+)\)$/m);
          if (!code.startsWith("# axonx:workspace-text\n") || !settings)
            throw new Error("Playground only simulates workspace source reads");
          const [, path, limit] = JSON.parse(JSON.parse(settings[1]));
          const source = sourceFiles.get(path);
          if (source === undefined)
            throw new Error(`Demo source not found: ${path}`);
          const bytes = new TextEncoder().encode(source);
          const data = btoa(
            Array.from(bytes.slice(0, limit), (byte) =>
              String.fromCharCode(byte),
            ).join(""),
          );
          return response({
            stdout: JSON.stringify({ data, truncated: bytes.length > limit }),
            stderr: "",
            exit_code: 0,
            stdout_truncated: false,
            stderr_truncated: false,
          });
        }
        case "list_machines":
          return response([]);
        case "machine_status":
          return response({
            axonx: {
              version: contracts.version,
              git_commit: null,
              git_branch: "playground",
            },
            cpu: {
              total_cores: 4,
              physical_cores: 4,
              usage_percent: 3,
            },
            memory: {
              total_bytes: 8589934592,
              used_bytes: 2147483648,
              available_bytes: 6442450944,
              usage_percent: 25,
            },
            gpus: [],
          });
        case "list_task_defs":
          return response(
            args.include_schemas === false
              ? definitions.map(({ input_schema, output_schema, ...info }) => {
                  void input_schema;
                  void output_schema;
                  return info;
                })
              : definitions,
          );
        case "get_task_def": {
          const definition = definitions.find(
            (task) => task.name === args.task,
          );
          if (!definition) throw new Error(`Unknown Task: ${args.task}`);
          return response(definition);
        }
        case "list_task_ids":
          return response(
            [...tasks.values()]
              .sort(
                (a, b) =>
                  Date.parse(b.created_at || "") -
                    Date.parse(a.created_at || "") ||
                  b.task_id.localeCompare(a.task_id),
              )
              .map((task) => task.task_id),
          );
        case "list_task_statuses":
          return response(
            [...tasks.values()]
              .filter(
                (task) =>
                  (!args.task_type || task.task_type === args.task_type) &&
                  (!args.state || task.state === args.state),
              )
              .sort(
                (a, b) =>
                  Date.parse(b.created_at || "") -
                    Date.parse(a.created_at || "") ||
                  b.task_id.localeCompare(a.task_id),
              )
              .map((task) => taskView(task, args.detail ?? "summary")),
          );
        case "status":
          return response(taskView(requiredTask(id), args.detail));
        case "read_task_log":
          if (
            args.started_at &&
            requiredTask(id).started_at !== args.started_at
          )
            throw new Error(`Task restarted: ${id}`);
          return response(
            logChunk(id, Number(args.offset ?? -1), Number(args.limit ?? 8192)),
          );
        case "list_entries":
          return response(
            directory(String(args.path || ""), Number(args.offset || 0)),
          );
        case "list_task_directories": {
          const dir = directory(String(args.path));
          dir.entries = dir.entries.filter((entry) =>
            files.has(`${entry.path}/metadata.json`),
          );
          return response(dir);
        }
        case "preview_file": {
          const file = files.get(String(args.path));
          if (!file) throw new Error(`Demo file not found: ${args.path}`);
          const maxBytes =
            args.max_bytes === undefined ? undefined : Number(args.max_bytes);
          if (
            maxBytes !== undefined &&
            (!Number.isInteger(maxBytes) || maxBytes < 1 || maxBytes > 33554432)
          )
            throw new Error("Invalid max_bytes");
          if (
            file.kind === "parquet" ||
            file.kind === "csv" ||
            file.kind === "jsonl"
          ) {
            const offset = Number(args.offset || 0);
            const limit = Number(args.limit ?? 200);
            if (
              !Number.isInteger(offset) ||
              !Number.isInteger(limit) ||
              offset < 0 ||
              limit < 1
            )
              throw new Error("Invalid preview pagination");
            return response({
              ...file,
              offset,
              limit,
              rows: file.rows.slice(offset, offset + limit),
              has_more: offset + limit < file.rows.length,
            });
          }
          if (maxBytes !== undefined) {
            const structured = file.kind === "json" || file.kind === "yaml";
            const content = structured
              ? JSON.stringify(file.data, null, 2)
              : "content" in file
                ? file.content
                : "";
            const bytes = new TextEncoder().encode(content);
            if (bytes.length > maxBytes)
              return response({
                ...file,
                content: new TextDecoder("utf-8", { fatal: true }).decode(
                  bytes.slice(0, maxBytes),
                  { stream: true },
                ),
                truncated: true,
                ...(structured
                  ? {
                      data: null,
                      parse_error:
                        "Partial preview; increase max_bytes to parse the complete file",
                    }
                  : {}),
              });
          }
          return response(file);
        }
        case "delete_entries": {
          const paths = args.paths as string[];
          for (const taskId of tasks.keys())
            if (paths.some((path) => taskDirectory(taskId) === path))
              tasks.delete(taskId);
          for (const path of paths)
            for (const key of files.keys())
              if (key === path || key.startsWith(`${path}/`)) files.delete(key);
          return response(
            paths.map((path) => ({ deleted: path, kind: "directory" })),
          );
        }
        case "get_task_graph": {
          requiredTask(id);
          const connected = new Set([id]);
          for (const nodeId of connected) {
            const task = tasks.get(nodeId);
            for (const upstreamId of upstreamTaskIds(
              task?.input_params.upstream_task_ids,
            ))
              connected.add(upstreamId);
            for (const downstreamTask of tasks.values())
              if (
                upstreamTaskIds(
                  downstreamTask.input_params.upstream_task_ids,
                ).includes(nodeId)
              )
                connected.add(downstreamTask.task_id);
          }
          const nodes = [...connected].map((nodeId) => {
            const task = tasks.get(nodeId);
            return {
              task_id: nodeId,
              kind: task?.task_type || nodeId.split("#")[0],
              task_name: task?.reg_name || null,
              created_at: task?.created_at || null,
              upstream_task_ids: upstreamTaskIds(
                task?.input_params.upstream_task_ids,
              ),
              state: task?.state || null,
              missing: !task,
              provisional: !!task && task.state !== "succeeded",
            };
          });
          return response({
            root_id:
              nodes.find((node) => !node.upstream_task_ids.length)?.task_id ||
              id,
            selected_id: id,
            nodes,
            edges: nodes.flatMap((node) =>
              node.upstream_task_ids.map((from) => ({
                from,
                to: node.task_id,
              })),
            ),
          });
        }
        default:
          throw new Error(
            `Unsupported Playground Job / 未支持的演示接口: ${name}`,
          );
      }
    } catch (error) {
      return response(
        error instanceof Error ? error.message : String(error),
        false,
      );
    }
  };
  return transport;
}
