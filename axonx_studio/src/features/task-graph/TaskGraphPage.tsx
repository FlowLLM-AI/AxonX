import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, ChevronRight, GitBranch, Search } from "lucide-react";
import { callJob, remoteBody } from "../../shared/api/client";
import type { AppRoute, SectionId } from "../../app/routes";
import type { ContextOption, Language } from "../../types";

type Kind = "base" | "api" | "etl" | "analysis" | "train" | "predict" | "inference" | "backtest";
interface TaskNode {
  task_id: string;
  kind: Kind;
  task_name: string | null;
  created_at: string | null;
  parent_ids: string[];
  missing: boolean;
  root_id?: string;
}
interface TaskList { items: TaskNode[]; total: number; offset: number; limit: number }
interface TaskGraph { root_id: string; selected_id: string; nodes: TaskNode[]; edges: { from: string; to: string }[] }

const labels: Record<Kind, [string, string]> = {
  base: ["基础任务", "Base task"],
  api: ["API", "API"],
  etl: ["ETL", "ETL"],
  analysis: ["因子分析", "Factor analysis"],
  train: ["模型训练", "Training"],
  predict: ["离线预测", "Prediction"],
  inference: ["在线推理", "Inference"],
  backtest: ["离线回测", "Backtest"],
};
const sectionFor: Record<Kind, SectionId> = {
  base: "runtime", api: "runtime", etl: "etl", analysis: "factors", train: "train", predict: "predict", inference: "runtime", backtest: "backtest",
};

function taskTime(node: TaskNode): string | null {
  const stamp = node.task_id.match(/^[^#]+#[^#]+#[^#]+#(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$/);
  if (stamp) return `${stamp[1]}-${stamp[2]}-${stamp[3]} ${stamp[4]}:${stamp[5]}`;
  if (!node.created_at) return null;
  const date = new Date(node.created_at);
  return Number.isNaN(date.getTime()) ? null : date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function shortTaskId(taskId: string): string {
  return `#${taskId.split("#")[2] || taskId}`;
}

export function TaskGraphPage({ language, remoteIp, selectedId, onSelect, onNavigate, onOptionsChange, onConnection }: {
  language: Language;
  remoteIp?: string;
  selectedId?: string;
  onSelect: (taskId: string) => void;
  onNavigate: (section: AppRoute["section"], taskId: string) => void;
  onOptionsChange: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [items, setItems] = useState<TaskNode[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [graph, setGraph] = useState<TaskGraph | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [listError, setListError] = useState("");
  const [graphError, setGraphError] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  useEffect(() => { setOffset(0); setItems([]); }, [debounced, remoteIp]);
  useEffect(() => {
    const controller = new AbortController();
    setLoadingList(true);
    setListError("");
    callJob<TaskList>("list_task_graphs", { q: debounced, offset, limit: 50, ...remoteBody(remoteIp) }, controller.signal)
      .then((result) => { setItems((previous) => offset === 0 ? result.items : [...previous, ...result.items]); setTotal(result.total); onConnection(true); })
      .catch((error) => { if (!controller.signal.aborted) { setListError(String(error)); onConnection(false); } })
      .finally(() => { if (!controller.signal.aborted) setLoadingList(false); });
    return () => controller.abort();
  }, [debounced, offset, remoteIp, onConnection]);
  useEffect(() => {
    onOptionsChange(items.map((node) => ({ value: node.task_id, label: node.task_id, detail: labels[node.kind][zh ? 0 : 1] })));
  }, [items, onOptionsChange, zh]);
  useEffect(() => {
    if (!selectedId) { setGraph(null); setGraphError(""); return; }
    const controller = new AbortController();
    setLoadingGraph(true);
    setGraphError("");
    setCollapsed(new Set());
    callJob<TaskGraph>("get_task_graph", { task_id: selectedId, ...remoteBody(remoteIp) }, controller.signal)
      .then((result) => { setGraph(result); onConnection(true); })
      .catch((error) => { if (!controller.signal.aborted) { setGraph(null); setGraphError(String(error)); onConnection(false); } })
      .finally(() => { if (!controller.signal.aborted) setLoadingGraph(false); });
    return () => controller.abort();
  }, [selectedId, remoteIp, onConnection]);

  const children = useMemo(() => {
    const map = new Map<string, TaskNode[]>();
    for (const node of graph?.nodes || []) {
      const parentId = node.parent_ids[0];
      if (!parentId) continue;
      const siblings = map.get(parentId) || [];
      siblings.push(node);
      map.set(parentId, siblings);
    }
    return map;
  }, [graph]);
  const nodeById = useMemo(() => new Map(graph?.nodes.map((node) => [node.task_id, node]) || []), [graph]);
  const roots = useMemo(() => graph?.nodes.filter((node) => node.parent_ids.length === 0) || [], [graph]);
  const toggle = (taskId: string) => setCollapsed((previous) => {
    const next = new Set(previous);
    if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
    return next;
  });
  const renderNode = (node: TaskNode, ancestors = new Set<string>()): ReactNode => {
    if (ancestors.has(node.task_id)) return null;
    const nextAncestors = new Set(ancestors).add(node.task_id);
    const descendants = children.get(node.task_id) || [];
    const isCollapsed = collapsed.has(node.task_id);
    const time = taskTime(node);
    return (
      <li key={node.task_id}>
        <div className={`task-graph-node ${node.kind} ${node.task_id === selectedId ? "selected" : ""} ${node.missing ? "missing" : ""}`}>
          {descendants.length > 0 && <button className="task-graph-toggle" onClick={() => toggle(node.task_id)} aria-label={isCollapsed ? (zh ? "展开" : "Expand") : (zh ? "折叠" : "Collapse")}>
            {isCollapsed ? <ChevronRight /> : <ChevronDown />}
          </button>}
          {descendants.length === 0 && <span className="task-graph-leaf" role="img" aria-label={zh ? "叶子节点" : "Leaf node"}>🍃</span>}
          {node.missing ? <div className="task-graph-content" title={node.task_id}><span className="task-graph-title"><span className="task-graph-type">{labels[node.kind][zh ? 0 : 1]}</span><span className="task-graph-short-id">{shortTaskId(node.task_id)}</span></span>{time && <time className="task-graph-time">{time}</time>}</div> : <button className="task-graph-link" onClick={() => onNavigate(sectionFor[node.kind], node.task_id)} title={node.task_id} aria-label={`${labels[node.kind][zh ? 0 : 1]} ${node.task_id}, ${zh ? "打开详情" : "Open details"}`}>
            <span className="task-graph-content"><span className="task-graph-title"><span className="task-graph-type">{labels[node.kind][zh ? 0 : 1]}</span><span className="task-graph-short-id">{shortTaskId(node.task_id)}</span></span>{time && <time className="task-graph-time">{time}</time>}</span>
          </button>}
          {node.missing && <small>{zh ? "产物缺失" : "Artifact missing"}</small>}
        </div>
        {node.parent_ids.length > 1 && <div className="task-graph-sources"><span>{zh ? "上游" : "Sources"}:</span>{node.parent_ids.map((parentId) => <button key={parentId} onClick={() => onSelect(parentId)} disabled={nodeById.get(parentId)?.missing} title={parentId}>{shortTaskId(parentId)}</button>)}</div>}
        {!isCollapsed && descendants.length > 0 && <ul>{descendants.map((child) => renderNode(child, nextAncestors))}</ul>}
      </li>
    );
  };

  return <div className="task-graph-page">
    <aside className="task-graph-list">
      <header><GitBranch /><div><h1>{zh ? "任务关系图" : "Task graph"}</h1><p>{zh ? "查看任务的全部上游依赖" : "Explore all upstream task dependencies"}</p></div></header>
      <label className="task-graph-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索所有 task ID" : "Search all task IDs"} /></label>
      <div className="task-graph-list-heading">{debounced ? (zh ? "搜索结果" : "Search results") : (zh ? "任务图" : "Task graphs")} <span>{total}</span></div>
      {listError && <p className="task-graph-message error">{listError}</p>}
      {loadingList && <p className="task-graph-message">{zh ? "加载中…" : "Loading…"}</p>}
      {!loadingList && !listError && items.length === 0 && <p className="task-graph-message">{zh ? "没有匹配的任务产物" : "No matching task artifacts"}</p>}
      <div className="task-graph-results">{items.map((node) => <button key={node.task_id} className={selectedId === node.task_id ? "active" : ""} onClick={() => onSelect(node.task_id)}>
        <span>{labels[node.kind][zh ? 0 : 1]}</span><code>{node.task_id}</code>
      </button>)}</div>
      {items.length < total && !loadingList && <button className="task-graph-more" onClick={() => setOffset(items.length)}>{zh ? "加载更多" : "Load more"}</button>}
    </aside>
    <main className="task-graph-canvas">
      {loadingGraph ? <p className="task-graph-message">{zh ? "加载关系图…" : "Loading graph…"}</p> : graphError ? <p className="task-graph-message error">{graphError}</p> : graph ? <>
        <header><div><small>{zh ? "根任务" : "Root task"}</small><h2 title={graph.root_id}>{labels[nodeById.get(graph.root_id)?.kind || "etl"][zh ? 0 : 1]} {shortTaskId(graph.root_id)}</h2>{nodeById.get(graph.root_id) && taskTime(nodeById.get(graph.root_id)!) && <time className="task-graph-root-time">{taskTime(nodeById.get(graph.root_id)!)}</time>}</div><span>{graph.nodes.length} {zh ? "个任务" : "tasks"}</span></header>
        <p className="task-graph-hint">{zh ? "点击节点打开任务详情" : "Click a node to open its details"}</p>
        <div className="task-graph-tree"><ul>{(roots.length ? roots : [nodeById.get(graph.root_id)!]).map((node) => renderNode(node))}</ul></div>
      </> : <div className="task-graph-empty"><GitBranch /><h2>{zh ? "选择或搜索任务图" : "Choose or search a task graph"}</h2><p>{zh ? "这里会显示任务及其上游依赖。" : "Tasks and their upstream dependencies will appear here."}</p></div>}
    </main>
  </div>;
}
