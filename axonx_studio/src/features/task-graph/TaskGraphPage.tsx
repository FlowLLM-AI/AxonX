import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { getTaskGraph } from "./api";
import type { TaskGraph, TaskGraphNode } from "./types";

const NODE_WIDTH = 216;
const NODE_HEIGHT = 68;
const COLUMN_GAP = 104;
const ROW_GAP = 28;
const PADDING = 32;

function taskIdentity(node: TaskGraphNode) {
  const [kind = node.kind, registration = node.task_name, name = node.task_id] =
    node.task_id.split("#");
  return {
    scope: registration
      ? `${kind.toUpperCase()}: ${registration}`
      : kind.toUpperCase(),
    name,
  };
}

function graphLayout(graph: TaskGraph) {
  const ids = new Set(graph.nodes.map((node) => node.task_id));
  const parents = new Map<string, string[]>();
  const children = new Map<string, string[]>();
  for (const node of graph.nodes) {
    parents.set(
      node.task_id,
      node.parent_ids.filter((parent) => ids.has(parent)),
    );
    children.set(node.task_id, []);
  }
  for (const edge of graph.edges) {
    if (ids.has(edge.from) && ids.has(edge.to))
      children.get(edge.from)?.push(edge.to);
  }

  const level = new Map<string, number>();
  const pending = graph.nodes
    .filter((node) => !(parents.get(node.task_id)?.length || 0))
    .map((node) => node.task_id);
  pending.forEach((id) => level.set(id, 0));
  while (pending.length) {
    const id = pending.shift()!;
    for (const child of children.get(id) || []) {
      const next = Math.max(level.get(child) || 0, (level.get(id) || 0) + 1);
      level.set(child, next);
      if (
        (parents.get(child) || []).every((parent) => level.has(parent)) &&
        !pending.includes(child)
      )
        pending.push(child);
    }
  }
  const fallback = Math.max(0, ...level.values()) + 1;
  graph.nodes.forEach((node) => {
    if (!level.has(node.task_id)) level.set(node.task_id, fallback);
  });

  const columns = new Map<number, TaskGraphNode[]>();
  graph.nodes.forEach((node) => {
    const value = level.get(node.task_id) || 0;
    columns.set(value, [...(columns.get(value) || []), node]);
  });
  const maxRows = Math.max(
    1,
    ...[...columns.values()].map((items) => items.length),
  );
  const height = Math.max(
    300,
    PADDING * 2 + maxRows * NODE_HEIGHT + (maxRows - 1) * ROW_GAP,
  );
  const width = Math.max(
    760,
    PADDING * 2 +
      columns.size * NODE_WIDTH +
      Math.max(0, columns.size - 1) * COLUMN_GAP,
  );
  const positions = new Map<string, { x: number; y: number }>();
  for (const [column, nodes] of columns) {
    const blockHeight =
      nodes.length * NODE_HEIGHT + (nodes.length - 1) * ROW_GAP;
    nodes.forEach((node, index) =>
      positions.set(node.task_id, {
        x: PADDING + column * (NODE_WIDTH + COLUMN_GAP),
        y: (height - blockHeight) / 2 + index * (NODE_HEIGHT + ROW_GAP),
      }),
    );
  }
  return { width, height, positions };
}

export function TaskGraphPanel({
  taskId,
  remoteIp,
  locateRequest,
  onOpenTask,
  onConnection,
}: {
  taskId: string;
  remoteIp?: string;
  locateRequest: number;
  onOpenTask: (taskId: string) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const [graph, setGraph] = useState<TaskGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const viewport = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getTaskGraph(taskId, remoteIp, controller.signal)
      .then((result) => {
        setGraph(result);
        onConnection(true);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setGraph(null);
          setError(reason instanceof Error ? reason.message : String(reason));
          onConnection(false);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [onConnection, remoteIp, taskId]);

  const layout = useMemo(() => (graph ? graphLayout(graph) : null), [graph]);
  const centerCurrent = useCallback(() => {
    if (!layout || !viewport.current) return;
    const point = layout.positions.get(taskId);
    if (!point) return;
    viewport.current.scrollTo({
      left: Math.max(
        0,
        point.x - viewport.current.clientWidth / 2 + NODE_WIDTH / 2,
      ),
      top: Math.max(
        0,
        point.y - viewport.current.clientHeight / 2 + NODE_HEIGHT / 2,
      ),
      behavior: "smooth",
    });
  }, [layout, taskId]);

  useEffect(() => {
    if (locateRequest) centerCurrent();
  }, [centerCurrent, locateRequest]);

  if (loading)
    return (
      <div className="task-relations-message">
        {t("taskGraph.loading_task_relationships")}
      </div>
    );
  if (error)
    return (
      <div className="task-relations-message error" role="alert">
        <AlertTriangle />
        <div>
          <strong>{t("taskGraph.unable_to_load_relationships")}</strong>
          <span>{error}</span>
        </div>
      </div>
    );
  if (!graph || !layout) return null;

  return (
    <div className="task-relations-panel">
      {graph.nodes.some((node) => node.provisional) && (
        <p className="task-relations-provisional">
          {t("taskGraph.some_tasks_use_provisional_relationships")}
        </p>
      )}
      <div className="task-relations-body">
        <div className="task-relations-viewport" ref={viewport}>
          <div
            className="task-relations-graph"
            style={{ width: layout.width, height: layout.height }}
          >
            <svg aria-hidden="true" width={layout.width} height={layout.height}>
              {graph.edges.map((edge) => {
                const from = layout.positions.get(edge.from);
                const to = layout.positions.get(edge.to);
                if (!from || !to) return null;
                const startX = from.x + NODE_WIDTH;
                const startY = from.y + NODE_HEIGHT / 2;
                const endX = to.x;
                const endY = to.y + NODE_HEIGHT / 2;
                const bend = (startX + endX) / 2;
                return (
                  <path
                    key={`${edge.from}:${edge.to}`}
                    d={`M ${startX} ${startY} C ${bend} ${startY}, ${bend} ${endY}, ${endX} ${endY}`}
                  />
                );
              })}
            </svg>
            {graph.nodes.map((node) => {
              const point = layout.positions.get(node.task_id)!;
              const identity = taskIdentity(node);
              return (
                <button
                  key={node.task_id}
                  className={`task-relation-node ${node.kind} ${node.task_id === taskId ? "current" : ""} ${node.missing ? "missing" : ""}`}
                  style={{
                    left: point.x,
                    top: point.y,
                    width: NODE_WIDTH,
                    height: NODE_HEIGHT,
                  }}
                  onClick={() => !node.missing && onOpenTask(node.task_id)}
                  disabled={node.missing}
                  title={node.missing ? undefined : t("taskGraph.open_task")}
                >
                  <span>
                    <strong>{identity.scope}</strong>
                    {node.state && (
                      <i className={`relation-state ${node.state}`}>
                        {t(`states.${node.state}`)}
                      </i>
                    )}
                  </span>
                  <code title={node.task_id}>{identity.name}</code>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
