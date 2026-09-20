import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ExternalLink,
  GitBranch,
  LocateFixed,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { getTaskGraph } from "./api";
import type { TaskGraph, TaskGraphNode } from "./types";

const NODE_WIDTH = 216;
const NODE_HEIGHT = 76;
const COLUMN_GAP = 104;
const ROW_GAP = 34;
const PADDING = 42;

function shortTaskId(taskId: string) {
  return `#${taskId.split("#")[2] || taskId}`;
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
    380,
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
  onOpenTask,
  onConnection,
}: {
  taskId: string;
  remoteIp?: string;
  onOpenTask: (taskId: string) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const [graph, setGraph] = useState<TaskGraph | null>(null);
  const [inspectedId, setInspectedId] = useState(taskId);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const viewport = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setInspectedId(taskId);
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
  const inspected = graph?.nodes.find((node) => node.task_id === inspectedId);
  const centerCurrent = () => {
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
  };

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

  const singleton = graph.nodes.length === 1;
  return (
    <section className="task-relations-panel">
      <header className="task-relations-toolbar">
        <div>
          <GitBranch />
          <span>
            <strong>{t("taskGraph.task_relationships")}</strong>
            <small>
              {singleton
                ? t("taskGraph.no_known_upstream_or_downstream")
                : `${graph.nodes.length} ${t("taskGraph.related_tasks")}`}
            </small>
          </span>
        </div>
        <button className="secondary-button" onClick={centerCurrent}>
          <LocateFixed />
          {t("taskGraph.locate_current_task")}
        </button>
      </header>
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
              return (
                <button
                  key={node.task_id}
                  className={`task-relation-node ${node.kind} ${node.task_id === taskId ? "current" : ""} ${node.task_id === inspectedId ? "inspected" : ""} ${node.missing ? "missing" : ""}`}
                  style={{
                    left: point.x,
                    top: point.y,
                    width: NODE_WIDTH,
                    height: NODE_HEIGHT,
                  }}
                  onClick={() => setInspectedId(node.task_id)}
                  aria-pressed={node.task_id === inspectedId}
                >
                  <span>
                    <strong>{t(`taskGraph.kinds.${node.kind}`)}</strong>
                    {node.state && (
                      <i className={`relation-state ${node.state}`}>
                        {t(`states.${node.state}`)}
                      </i>
                    )}
                  </span>
                  <code title={node.task_id}>{shortTaskId(node.task_id)}</code>
                  <small>
                    {node.missing
                      ? t("taskGraph.record_missing")
                      : node.task_name ||
                        (node.provisional ? t("taskGraph.provisional") : "")}
                  </small>
                </button>
              );
            })}
          </div>
        </div>
        {inspected && (
          <aside className="task-relation-inspector">
            <small>
              {inspected.task_id === taskId
                ? t("taskGraph.current_task")
                : t("taskGraph.selected_node")}
            </small>
            <h3>{t(`taskGraph.kinds.${inspected.kind}`)}</h3>
            <code>{inspected.task_id}</code>
            {inspected.task_name && <p>{inspected.task_name}</p>}
            {inspected.missing ? (
              <span className="missing-note">
                {t("taskGraph.the_task_record_was_deleted")}
              </span>
            ) : (
              <button
                className="primary-button"
                onClick={() => onOpenTask(inspected.task_id)}
              >
                <ExternalLink />
                {t("taskGraph.open_task_overview")}
              </button>
            )}
          </aside>
        )}
      </div>
    </section>
  );
}
