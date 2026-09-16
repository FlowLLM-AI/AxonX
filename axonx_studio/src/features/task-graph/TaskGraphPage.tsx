import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ArrowUpRight, ChevronDown, ChevronRight, GitBranch, Search } from "lucide-react";
import { callJob, remoteBody } from "../../shared/api/client";
import type { AppRoute, SectionId } from "../../app/routes";
import type { ContextOption, Language } from "../../types";

type Kind = "etl" | "analysis" | "training" | "predict" | "backtest";
interface TaskNode {
  task_id: string;
  kind: Kind;
  task_name: string | null;
  created_at: string | null;
  parent_id: string | null;
  missing: boolean;
  root_id?: string;
}
interface TaskList { items: TaskNode[]; total: number; offset: number; limit: number }
interface TaskGraph { root_id: string; selected_id: string; nodes: TaskNode[]; edges: { from: string; to: string }[] }

const labels: Record<Kind, [string, string]> = {
  etl: ["ETL", "ETL"],
  analysis: ["因子分析", "Factor analysis"],
  training: ["模型训练", "Training"],
  predict: ["离线预测", "Prediction"],
  backtest: ["离线回测", "Backtest"],
};
const sectionFor: Record<Kind, SectionId> = {
  etl: "etl", analysis: "factors", training: "training", predict: "predict", backtest: "backtest",
};

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
      if (!node.parent_id) continue;
      const siblings = map.get(node.parent_id) || [];
      siblings.push(node);
      map.set(node.parent_id, siblings);
    }
    return map;
  }, [graph]);
  const nodeById = useMemo(() => new Map(graph?.nodes.map((node) => [node.task_id, node]) || []), [graph]);
  const toggle = (taskId: string) => setCollapsed((previous) => {
    const next = new Set(previous);
    if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
    return next;
  });
  const renderNode = (node: TaskNode): ReactNode => {
    const descendants = children.get(node.task_id) || [];
    const isCollapsed = collapsed.has(node.task_id);
    return (
      <li key={node.task_id}>
        <div className={`task-graph-node ${node.kind} ${node.task_id === selectedId ? "selected" : ""} ${node.missing ? "missing" : ""}`}>
          {descendants.length > 0 && <button className="task-graph-toggle" onClick={() => toggle(node.task_id)} aria-label={isCollapsed ? (zh ? "展开" : "Expand") : (zh ? "折叠" : "Collapse")}>
            {isCollapsed ? <ChevronRight /> : <ChevronDown />}
          </button>}
          <span className="task-graph-type">{labels[node.kind][zh ? 0 : 1]}</span>
          {node.missing ? <code>{node.task_id}</code> : <button className="task-graph-link" onClick={() => onNavigate(sectionFor[node.kind], node.task_id)} title={zh ? "打开任务详情" : "Open task details"}>
            <code>{node.task_id}</code><ArrowUpRight />
          </button>}
          {node.missing && <small>{zh ? "产物缺失" : "Artifact missing"}</small>}
        </div>
        {!isCollapsed && descendants.length > 0 && <ul>{descendants.map(renderNode)}</ul>}
      </li>
    );
  };

  return <div className="task-graph-page">
    <aside className="task-graph-list">
      <header><GitBranch /><div><h1>{zh ? "任务关系图" : "Task graph"}</h1><p>{zh ? "从 ETL 追踪分析、训练、预测和回测" : "Trace analysis, training, predictions and backtests"}</p></div></header>
      <label className="task-graph-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索所有 task ID" : "Search all task IDs"} /></label>
      <div className="task-graph-list-heading">{debounced ? (zh ? "搜索结果" : "Search results") : (zh ? "ETL 任务" : "ETL tasks")} <span>{total}</span></div>
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
        <header><div><small>{zh ? "根任务" : "Root task"}</small><h2>{graph.root_id}</h2></div><span>{graph.nodes.length} {zh ? "个任务" : "tasks"}</span></header>
        <p className="task-graph-hint">{zh ? "高亮为当前搜索或选中的任务；点击任意 task ID 打开详情。" : "The selected task is highlighted. Click any task ID to open its details."}</p>
        <div className="task-graph-tree">{nodeById.get(graph.root_id) ? <ul>{renderNode(nodeById.get(graph.root_id)!)}</ul> : <p className="task-graph-message">{zh ? "根任务缺失" : "Root task missing"}</p>}</div>
      </> : <div className="task-graph-empty"><GitBranch /><h2>{zh ? "选择一个 ETL 或搜索任意 task ID" : "Choose an ETL or search any task ID"}</h2><p>{zh ? "这里会显示从 ETL 到回测的完整任务关系。" : "The complete task graph from ETL to backtest will appear here."}</p></div>}
    </main>
  </div>;
}
