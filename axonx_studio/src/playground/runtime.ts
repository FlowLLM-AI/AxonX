import type { TaskMetadata, TaskSummary } from "../features/tasks/types";
import { isOnlineTask } from "../features/online/types";
import { taskStepProgress } from "../features/tasks/format";
import type { WorkspaceListing } from "../features/workspace/types";
import type { Transport } from "../shared/api/client";
import type { JobEvent } from "../shared/api/event";
import { parseSourceTasks } from "../shared/lib/sourceTasks";
import { createAgent } from "./agent";
import { catalog } from "./catalog";
import {
  addArtifacts,
  definitions,
  epoch,
  json,
  schedules,
  studioPages,
  seed,
  taskStatus,
} from "./fixtures";
import { sse } from "./stream";

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
    is_online: isOnlineTask(task),
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
  const { tasks, files } = seed();
  const agent = createAgent();
  let serial = 0;
  const running = new Map<string, number>();
  const requiredTask = (id: string) => {
    const task = tasks.get(id);
    if (!task) throw new Error(`Unknown demo task: ${id}`);
    return task;
  };
  function updateTasks() {
    for (const [id, started] of running) {
      const task = requiredTask(id);
      const elapsed = Date.now() - started;
      task.state = elapsed < 600 ? "queued" : "running";
      task.managed_run_id = task.run_id;
      task.started_at =
        elapsed < 600 ? null : new Date(started + 600).toISOString();
      task.steps = task.steps.map((step, i) => ({
        ...step,
        percentage: Math.max(0, Math.min(100, (elapsed - 600 - i * 1800) / 18)),
        started_at:
          elapsed >= 600 + i * 1800
            ? new Date(started + 600 + i * 1800).toISOString()
            : null,
        finished_at:
          elapsed >= 2400 + i * 1800
            ? new Date(started + 2400 + i * 1800).toISOString()
            : null,
      }));
      if (elapsed >= 6000) {
        running.delete(id);
        task.finished_at = new Date(started + 6000).toISOString();
        task.state =
          task.input_params.outcome === "failure" ? "failed" : "succeeded";
        task.managed_run_id = null;
        if (task.state === "failed") {
          task.error = "Simulated missing input / 模拟输入缺失";
          task.exit_code = 1;
        } else {
          task.output_params = { output_dir: `${id.split("#")[0]}/${id}` };
          addArtifacts(
            files,
            task,
            String(task.input_params.strategy),
            parseSourceTasks(task.input_params.source_tasks),
          );
        }
      }
    }
    for (const task of tasks.values())
      files.set(`${task.task_type}/${task.task_id}/metadata.json`, json(task));
  }
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
  return async (url, init = {}) => {
    if (init.signal?.aborted) throw abortError();
    updateTasks();
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
        if (name === "stream_task") {
          requiredTask(id);
          return sse(() => {
            updateTasks();
            const task = requiredTask(id);
            const events: JobEvent[] = [
              ...task.steps.map((step) => ({
                kind: "progress" as const,
                ...step,
              })),
              { kind: "log", ...logChunk(id), reset: true },
            ];
            if (!running.has(id)) {
              for (const [path, file] of files)
                if (path.startsWith(`${id.split("#")[0]}/${id}/`))
                  events.push({
                    kind: "artifact",
                    path,
                    size: file.size,
                    sha256: "",
                    media_type:
                      file.kind === "json" ? "application/json" : null,
                    extra: { simulated: true },
                  });
              events.push(terminal(task));
            }
            return events;
          }, init.signal);
        }
        if (name === "agent_chat") return agent.stream(args, init.signal);
        throw new Error(`Unsupported demo stream: ${name}`);
      }
      if (parsed.pathname === "/jobs") return response(catalog);
      if (Object.hasOwn(agent.jobs, name))
        return response(agent.jobs[name](args));
      switch (name) {
        case "list_machines":
          return response([]);
        case "machine_status":
          return response({
            axonx: {
              version: "0.1.0-demo",
              git_commit: null,
              git_branch: "playground",
            },
            cpu: {
              total_cores: 4,
              physical_cores: 4,
              usage_percent: running.size ? 42 : 3,
            },
            memory: {
              total_bytes: 8589934592,
              used_bytes: 2147483648,
              available_bytes: 6442450944,
              usage_percent: 25,
            },
            gpus: [],
          });
        case "list_installed_task_definitions":
          return response(
            args.include_schemas === false
              ? definitions.map(({ input_schema, output_schema, ...info }) => {
                  void input_schema;
                  void output_schema;
                  return info;
                })
              : definitions,
          );
        case "list_studio_pages":
          return response(studioPages);
        case "list_schedules":
          return response(
            schedules
              .filter((schedule) => !args.name || schedule.name === args.name)
              .map((schedule) => {
                const { history, last_trigger, ...config } = schedule;
                if (args.include_history)
                  return {
                    ...config,
                    last_trigger,
                    history_total: (history || []).length,
                    history_scheduler_ids: [
                      ...new Set(
                        (history || [])
                          .filter((run) => run.job === schedule.job)
                          .map((run) => run.scheduler_id)
                          .filter((id): id is string => id !== null),
                      ),
                    ],
                    history: (history || []).slice(
                      -Number(args.history_limit ?? 20),
                    ),
                  };
                if (!last_trigger) return { ...config, last_trigger };
                const { result, ...trigger } = last_trigger;
                void result;
                return { ...config, last_trigger: trigger };
              }),
          );
        case "list_task_statuses":
          return response(
            [...tasks.values()]
              .filter(
                (task) =>
                  (!args.task_type || task.task_type === args.task_type) &&
                  (!args.state || task.state === args.state),
              )
              .reverse()
              .map((task) => taskView(task, args.detail ?? "summary")),
          );
        case "status":
          return response(taskView(requiredTask(id), args.detail));
        case "read_task_log":
          if (args.run_id && requiredTask(id).run_id !== args.run_id)
            throw new Error(`Task run changed: ${id}`);
          return response(
            logChunk(id, Number(args.offset ?? -1), Number(args.limit ?? 8192)),
          );
        case "submit": {
          const definition = definitions.find(
            (definition) => definition.name === args.task,
          );
          if (!definition)
            throw new Error("Select a playground task definition");
          if (
            args.strategy &&
            !["steady", "volatile"].includes(String(args.strategy))
          )
            throw new Error("Unknown demo strategy");
          if (
            args.outcome &&
            !["success", "failure"].includes(String(args.outcome))
          )
            throw new Error("Unknown demo outcome");
          const id = `${definition.task_type}#submitted-${++serial}`;
          const task = taskStatus(
            definition.task_type as TaskMetadata["task_type"],
            id,
            String(args.task_name || `Demo ${definition.task_type}`),
          );
          const upstream = (
            {
              analysis: "etl#demo",
              train: "etl#demo",
              predict: "train#demo",
              backtest: "predict#demo",
            } as Partial<Record<TaskMetadata["task_type"], string>>
          )[definition.task_type];
          task.input_params = {
            ...args,
            strategy: args.strategy || "steady",
            source_tasks: upstream && tasks.has(upstream) ? upstream : "",
          };
          task.created_at = new Date().toISOString();
          task.started_at = null;
          task.finished_at = null;
          task.state = "queued";
          task.managed_run_id = task.run_id;
          task.output_params = {};
          task.steps = task.steps.map((step) => ({
            ...step,
            percentage: 0,
            started_at: null,
            finished_at: null,
          }));
          tasks.set(id, task);
          running.set(id, Date.now());
          return response({ task_id: id, run_id: id, task: definition.name });
        }
        case "cancel": {
          if (!args.task_id && !args.run_id)
            throw new Error("Cancellation requires task_id or run_id");
          const task = args.task_id
            ? tasks.get(String(args.task_id))
            : [...tasks.values()].find((task) => task.run_id === args.run_id);
          if (!task || (args.run_id && args.run_id !== task.run_id))
            return response(false);
          if (!running.delete(task.task_id)) return response(false);
          task.state = "cancelled";
          task.managed_run_id = null;
          task.finished_at = new Date().toISOString();
          return response(true);
        }
        case "delete_tasks": {
          const ids = args.task_ids as string[];
          for (const id of ids) requiredTask(id);
          for (const id of ids) {
            running.delete(id);
            tasks.delete(id);
            for (const path of files.keys())
              if (path.startsWith(`${id.split("#")[0]}/${id}/`))
                files.delete(path);
          }
          return response(ids);
        }
        case "list_entries":
          return response(
            directory(String(args.path || ""), Number(args.offset || 0)),
          );
        case "list_task_runs": {
          const dir = directory(String(args.task_type));
          dir.entries = dir.entries.filter(
            (entry) => tasks.get(entry.name)?.task_type === args.task_type,
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
            for (const parent of parseSourceTasks(
              task?.input_params.source_tasks,
            ))
              connected.add(parent);
            for (const child of tasks.values())
              if (
                parseSourceTasks(child.input_params.source_tasks).includes(
                  nodeId,
                )
              )
                connected.add(child.task_id);
          }
          const nodes = [...connected].map((nodeId) => {
            const task = tasks.get(nodeId);
            return {
              task_id: nodeId,
              kind: task?.task_type || nodeId.split("#")[0],
              task_name: task?.reg_name || null,
              created_at: task?.created_at || null,
              parent_ids: parseSourceTasks(task?.input_params.source_tasks),
              state: task?.state || null,
              missing: !task,
              provisional: !!task && task.state !== "succeeded",
            };
          });
          return response({
            root_id:
              nodes.find((node) => !node.parent_ids.length)?.task_id || id,
            selected_id: id,
            nodes,
            edges: nodes.flatMap((node) =>
              node.parent_ids.map((from) => ({ from, to: node.task_id })),
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
}
