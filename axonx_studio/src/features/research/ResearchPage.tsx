import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  Check,
  CheckCircle2,
  CheckSquare2,
  Copy,
  Database,
  FileSpreadsheet,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import {
  deleteWorkspaceEntries,
  listWorkspaceEntries,
  previewWorkspaceFile,
} from "../workspace/api";
import { formatBytes } from "../../shared/lib/format";
import { RailResizer } from "../../shared/ui/RailResizer";
import type { ContextOption, Language } from "../../types";
import type { ResearchArtifact, ResearchKind, ResearchPageId } from "./types";

const BacktestView = lazy(() =>
  import("./backtest/BacktestView").then((module) => ({
    default: module.BacktestView,
  })),
);

type Meta = ResearchArtifact;
type Kind = ResearchKind;

const copy = {
  analysis: {
    zh: ["分析结果", "查看分析指标与产物"],
    en: ["Analysis results", "Inspect analysis scores and artifacts"],
  },
  backtest: {
    zh: ["回测分析", "收益曲线、绩效指标与每日持仓检查"],
    en: [
      "Backtest analytics",
      "Equity curves, performance metrics, and daily holdings",
    ],
  },
  etl: {
    zh: ["ETL 数据集", "查看数据规模、列信息与产物"],
    en: ["ETL datasets", "Inspect dataset size, columns, and artifacts"],
  },
  train: {
    zh: ["模型管理", "查看模型、指标与生效参数"],
    en: ["Model registry", "Inspect models, metrics, and effective parameters"],
  },
  predict: {
    zh: ["预测结果", "查看样本范围、列信息与产物"],
    en: ["Predictions", "Inspect sample coverage, columns, and artifacts"],
  },
} as const;

const fmt = (value: unknown, digits = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (Math.abs(number) >= 1_000_000)
    return new Intl.NumberFormat("zh-CN", {
      notation: "compact",
      maximumFractionDigits: 2,
    }).format(number);
  return number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
};
function useTasks(
  kind: Kind,
  remoteIp?: string,
  onConnection?: (online: boolean) => void,
) {
  const [tasks, setTasks] = useState<Meta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setLoading(true);
    setError("");
    listWorkspaceEntries(kind, remoteIp, undefined, true)
      .then(async (directory) => {
        const dirs = directory.entries.filter(
          (entry) => entry.kind === "directory",
        );
        const values = await Promise.all(
          dirs.map(async (entry): Promise<Meta | null> => {
            try {
              const preview = await previewWorkspaceFile(
                `${entry.path}/metadata.json`,
                0,
                200,
                remoteIp,
              );
              if (
                !preview.data ||
                typeof preview.data !== "object" ||
                Array.isArray(preview.data)
              ) {
                throw new Error(preview.parse_error || "Invalid task metadata");
              }
              const metadata = preview.data as Record<string, unknown>;
              const output = (metadata.output_params || {}) as Record<
                string,
                unknown
              >;
              const input = (metadata.input_params || {}) as Record<
                string,
                unknown
              >;
              return {
                rows: output.rows,
                train_rows: output.train_rows,
                days: output.days,
                date_range: output.date_range,
                output_file: output.output_file,
                result_file: output.result_file,
                model_file: output.model_file,
                predictions_file: output.predictions_file,
                daily_file: output.daily_file,
                summary_file: output.summary_file,
                feature_columns: output.feature_columns,
                label_columns: output.label_columns,
                target_columns: output.target_columns,
                scores: output.scores,
                model_name: output.model_name,
                metrics: output.metrics,
                parameters: output.parameters,
                dimensions: output.dimensions,
                artifacts: (output.artifacts || {}) as Meta["artifacts"],
                task_key: String(metadata.reg_name),
                task_id: String(metadata.task_id),
                task_type: metadata.task_type as Kind,
                created_at: String(metadata.created_at),
                source: Array.isArray(input.source_tasks)
                  ? input.source_tasks.filter(
                      (item): item is string => typeof item === "string",
                    )
                  : [],
                config: {
                  task_id: String(metadata.task_id),
                  task_type: metadata.task_type as Kind,
                  task_name: String(input.task_name),
                  include_time: Boolean(input.include_time),
                  input_dir:
                    typeof input.input_dir === "string"
                      ? input.input_dir
                      : undefined,
                },
                _path: entry.path,
                _modified: entry.modified_at,
              } as Meta;
            } catch (reason) {
              console.warn(`Skipping task directory ${entry.path}:`, reason);
              return null;
            }
          }),
        );
        setTasks(
          values
            .filter((value): value is Meta => value !== null)
            .sort((a, b) =>
              String(b.created_at || b._modified).localeCompare(
                String(a.created_at || a._modified),
              ),
            ),
        );
        onConnection?.(true);
      })
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection?.(false);
      })
      .finally(() => setLoading(false));
  }, [kind, onConnection, remoteIp]);
  useEffect(() => {
    load();
  }, [load]);
  return { tasks, loading, error, load };
}

export function ResearchPage({
  kind,
  language,
  remoteIp,
  initialSelectedId,
  onSelected,
  onOptionsChange,
  onConnection,
  onNavigate,
}: {
  kind: Kind;
  language: Language;
  remoteIp?: string;
  initialSelectedId?: string;
  onSelected?: (taskId: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
  onNavigate: (page: ResearchPageId, resource?: string) => void;
}) {
  const zh = language === "zh";
  const labels = copy[kind][language];
  const { tasks, loading, error, load } = useTasks(
    kind,
    remoteIp,
    onConnection,
  );
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [selectionMode, setSelectionMode] = useState(false);
  const [checked, setChecked] = useState<Record<string, Meta>>({});
  const [deleteTargets, setDeleteTargets] = useState<Meta[]>([]);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [contextMenu, setContextMenu] = useState<{
    task: Meta;
    x: number;
    y: number;
  } | null>(null);
  useEffect(() => {
    if (!tasks.length) return;
    if (
      initialSelectedId &&
      tasks.some((task) => task.config.task_id === initialSelectedId)
    )
      setSelectedId(initialSelectedId);
    else if (!tasks.some((task) => task.config.task_id === selectedId))
      setSelectedId("");
  }, [tasks, selectedId, initialSelectedId]);
  useEffect(() => {
    onOptionsChange?.(
      tasks.map((task) => ({
        value: task.config.task_id,
        label: task.config.task_id,
        detail: task.task_key || kind,
      })),
    );
  }, [tasks, kind, onOptionsChange]);
  useEffect(() => {
    setSelectionMode(false);
    setChecked({});
    setDeleteTargets([]);
    setContextMenu(null);
  }, [kind, remoteIp]);
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("blur", close);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", close, true);
    };
  }, [contextMenu]);
  const selected = tasks.find((task) => task.config.task_id === selectedId);
  const visible = tasks.filter((task) =>
    `${task.config.task_id} ${task.task_key}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const selectedCount = Object.keys(checked).length;
  const allVisibleSelected =
    visible.length > 0 && visible.every((task) => checked[task._path]);
  const toggleTask = (task: Meta) =>
    setChecked((current) => {
      const next = { ...current };
      if (next[task._path]) delete next[task._path];
      else next[task._path] = task;
      return next;
    });
  const toggleVisible = () =>
    setChecked((current) => {
      const next = { ...current };
      for (const task of visible) {
        if (allVisibleSelected) delete next[task._path];
        else next[task._path] = task;
      }
      return next;
    });
  const confirmDelete = async () => {
    if (!deleteTargets.length) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteWorkspaceEntries(
        deleteTargets.map((task) => task._path),
        remoteIp,
      );
      setDeleteTargets([]);
      setChecked({});
      setSelectionMode(false);
      load();
      onConnection(true);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
    } finally {
      setDeleting(false);
    }
  };
  return (
    <section className="workspace-page research-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">RESEARCH / {kind.toUpperCase()}</p>
          <h1>{labels[0]}</h1>
          <span>{labels[1]}</span>
        </div>
        {kind !== "etl" && (
          <button className="secondary-button" onClick={load}>
            <RefreshCw className={loading ? "spin" : ""} />
            {zh ? "刷新" : "Refresh"}
          </button>
        )}
      </div>
      {error && (
        <div className="error-banner">
          <AlertTriangle />
          <div>
            <strong>
              {zh ? "无法读取任务产物" : "Unable to load artifacts"}
            </strong>
            <span>{error}</span>
          </div>
        </div>
      )}
      <div className="research-layout">
        <aside
          className={`run-index rail-panel ${selectionMode ? "selecting" : ""}`}
        >
          <header className="run-index-header rail-header">
            <div className="run-index-heading rail-heading">
              <small>TASK VERSIONS</small>
              <strong>{zh ? "任务版本" : "Task versions"}</strong>
            </div>
            <div className="run-index-tools">
              <em>{tasks.length}</em>
              <button
                className="run-index-refresh rail-refresh"
                aria-label={zh ? "刷新" : "Refresh"}
                onClick={load}
              >
                <RefreshCw className={loading ? "spin" : ""} />
              </button>
            </div>
          </header>
          <label className="run-index-search rail-search">
            <Search />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={zh ? "搜索 task_id" : "Search task_id"}
            />
          </label>
          <div className="rail-scroll">
            {loading && !tasks.length ? (
              <span className="run-loading">
                <LoaderCircle className="spin" />
              </span>
            ) : (
              visible.map((task) => (
                <article
                  className={`${selectedId === task.config.task_id ? "active" : ""} ${checked[task._path] ? "checked" : ""}`}
                  key={task.config.task_id}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    setContextMenu({
                      task,
                      x: Math.max(
                        6,
                        Math.min(event.clientX, window.innerWidth - 224),
                      ),
                      y: Math.max(
                        6,
                        Math.min(event.clientY, window.innerHeight - 150),
                      ),
                    });
                  }}
                >
                  {selectionMode && (
                    <button
                      className="run-check"
                      aria-label={`${zh ? "选择" : "Select"} ${task.config.task_id}`}
                      onClick={() => toggleTask(task)}
                    >
                      {checked[task._path] && <Check />}
                    </button>
                  )}
                  <button
                    className="run-main rail-list-item"
                    onClick={() =>
                      selectionMode
                        ? toggleTask(task)
                        : (setSelectedId(task.config.task_id),
                          onSelected?.(task.config.task_id))
                    }
                  >
                    <span
                      className={`run-item-avatar rail-avatar run-kind-${kind}`}
                    >
                      {String(task.task_key || kind)
                        .trim()
                        .slice(0, 1)
                        .toUpperCase()}
                    </span>
                    <span className="rail-item-copy">
                      <strong>{task.task_key || kind}</strong>
                      <code>{task.config.task_id}</code>
                      <small>
                        {task.created_at
                          ? new Date(task.created_at).toLocaleString(
                              language === "zh" ? "zh-CN" : "en",
                            )
                          : zh
                            ? "元数据不可用"
                            : "Metadata unavailable"}
                      </small>
                    </span>
                    {!selectionMode && <ArrowRight />}
                  </button>
                </article>
              ))
            )}
          </div>
          {selectionMode && (
            <footer className="run-selection">
              <span>
                <strong>{selectedCount}</strong>
                {zh ? " 个已选" : " selected"}
              </span>
              <button
                onClick={() => {
                  setSelectionMode(false);
                  setChecked({});
                }}
              >
                {zh ? "完成" : "Done"}
              </button>
              <button onClick={toggleVisible}>
                {allVisibleSelected
                  ? zh
                    ? "取消全选"
                    : "Deselect"
                  : zh
                    ? "全选"
                    : "Select all"}
              </button>
              <button
                className="danger"
                disabled={!selectedCount}
                onClick={() => {
                  setDeleteTargets(Object.values(checked));
                  setDeleteError("");
                }}
              >
                <Trash2 />
                {zh ? "删除" : "Delete"}
              </button>
            </footer>
          )}
        </aside>
        <RailResizer min={180} max={460} className="context-resizer" />
        <main className="research-canvas">
          {selected ? (
            <ArtifactDetail
              kind={kind}
              meta={selected}
              language={language}
              remoteIp={remoteIp}
              onNavigate={onNavigate}
            />
          ) : (
            !loading && (
              <div className="empty-research">
                <Database />
                <strong>
                  {tasks.length
                    ? zh
                      ? "选择一个任务版本"
                      : "Select a task version"
                    : zh
                      ? `暂无 ${kind} 任务`
                      : `No ${kind} tasks`}
                </strong>
                <span>
                  {tasks.length
                    ? zh
                      ? "右侧将显示该任务的数据与产物。"
                      : "Its data and artifacts will appear here."
                    : zh
                      ? "任务产出后会自动出现在这里。"
                      : "Task artifacts will appear here automatically."}
                </span>
              </div>
            )
          )}
        </main>
      </div>
      {contextMenu && (
        <div
          className="workspace-context-menu task-version-context-menu"
          role="menu"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <header>
            <span>{contextMenu.task.config.task_id}</span>
            <small>{contextMenu.task.task_key || kind}</small>
          </header>
          <button
            role="menuitem"
            onClick={() => {
              setSelectionMode(true);
              if (!checked[contextMenu.task._path])
                toggleTask(contextMenu.task);
              setContextMenu(null);
            }}
          >
            <CheckSquare2 />
            {zh ? "多选" : "Select"}
          </button>
          <button
            className="danger"
            role="menuitem"
            onClick={() => {
              setDeleteTargets([contextMenu.task]);
              setDeleteError("");
              setContextMenu(null);
            }}
          >
            <Trash2 />
            {zh ? "删除" : "Delete"}
          </button>
        </div>
      )}
      {deleteTargets.length > 0 && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={() => !deleting && setDeleteTargets([])}
        >
          <div
            className="confirm-modal workspace-delete-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="task-version-delete-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="close-button"
              aria-label={zh ? "取消" : "Cancel"}
              disabled={deleting}
              onClick={() => setDeleteTargets([])}
            >
              <X />
            </button>
            <div className="danger-icon">
              <Trash2 />
            </div>
            <h2 id="task-version-delete-title">
              {deleteTargets.length > 1
                ? zh
                  ? "删除所选任务版本？"
                  : "Delete selected task versions?"
                : zh
                  ? "删除这个任务版本？"
                  : "Delete this task version?"}
            </h2>
            <div className="workspace-delete-list">
              {deleteTargets.slice(0, 6).map((task) => (
                <code key={task._path}>{task.config.task_id}</code>
              ))}
              {deleteTargets.length > 6 && (
                <span>+{deleteTargets.length - 6}</span>
              )}
            </div>
            <p>
              {zh
                ? "对应任务目录及其中的产物文件会被永久删除，此操作无法撤销。"
                : "The task directories and all artifact files inside them will be permanently deleted. This cannot be undone."}
            </p>
            {deleteError && (
              <div className="inline-error">
                <strong>{zh ? "删除失败" : "Delete failed"}</strong>
                <span>{deleteError}</span>
              </div>
            )}
            <div>
              <button
                className="secondary-button"
                disabled={deleting}
                onClick={() => setDeleteTargets([])}
              >
                {zh ? "取消" : "Cancel"}
              </button>
              <button
                className="danger-button"
                disabled={deleting}
                onClick={() => void confirmDelete()}
              >
                {deleting ? <LoaderCircle className="spin" /> : <Trash2 />}
                {deleting
                  ? zh
                    ? "删除中…"
                    : "Deleting…"
                  : `${zh ? "确认删除" : "Delete"} (${deleteTargets.length})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function ArtifactDetail({
  kind,
  meta,
  language,
  remoteIp,
  onNavigate,
}: {
  kind: Kind;
  meta: Meta;
  language: Language;
  remoteIp?: string;
  onNavigate: (page: ResearchPageId, resource?: string) => void;
}) {
  const zh = language === "zh";
  const [copiedLineage, setCopiedLineage] = useState("");
  const pageByType: Partial<Record<string, ResearchPageId>> = {
    etl: "etl",
    analysis: "factors",
    train: "train",
    predict: "predict",
    backtest: "backtest",
  };
  const upstreams = (meta.source || []).map((taskId) => ({
    taskId,
    type: taskId.split("#")[0],
    page: pageByType[taskId.split("#")[0]],
  }));
  const copyLineageId = async (taskId: string) => {
    await navigator.clipboard.writeText(taskId);
    setCopiedLineage(taskId);
    window.setTimeout(
      () => setCopiedLineage((current) => (current === taskId ? "" : current)),
      1600,
    );
  };
  return (
    <>
      {
        <header className="artifact-header">
          <div>
            <span className={`artifact-kind ${kind}`}>{iconFor(kind)}</span>
            <div>
              <small>{meta.task_key || kind}</small>
              <h2>{meta.config.task_id}</h2>
            </div>
          </div>
          <span className="ready-badge">
            <CheckCircle2 />
            {zh ? "产物就绪" : "Artifacts ready"}
          </span>
        </header>
      }
      {upstreams.length > 0 && (
        <div className="lineage-strip">
          <span>
            <GitBranch />
            {zh ? "数据血缘" : "LINEAGE"}
          </span>
          <div className="lineage-sources">
            {upstreams.map((upstream) => (
              <div className="lineage-node" key={upstream.taskId}>
                {upstream.page ? (
                  <button
                    className="lineage-link"
                    onClick={() => onNavigate(upstream.page!, upstream.taskId)}
                    title={zh ? "打开上游任务" : "Open upstream task"}
                  >
                    <em>{upstream.type.toUpperCase()}</em>
                    <code>{upstream.taskId}</code>
                    <ArrowRight />
                  </button>
                ) : (
                  <strong>
                    <em>{upstream.type.toUpperCase()}</em>
                    <code>{upstream.taskId}</code>
                  </strong>
                )}
                <button
                  className="lineage-copy"
                  onClick={() => void copyLineageId(upstream.taskId)}
                  aria-label={zh ? "复制上游 Task ID" : "Copy upstream task ID"}
                >
                  {copiedLineage === upstream.taskId ? <Check /> : <Copy />}
                </button>
              </div>
            ))}
          </div>
          <i />
          <div className="lineage-node current">
            <strong>
              <em>{kind.toUpperCase()}</em>
              <code>{meta.config.task_id}</code>
            </strong>
            <button
              className="lineage-copy"
              onClick={() => void copyLineageId(meta.config.task_id)}
              aria-label={zh ? "复制当前 Task ID" : "Copy current task ID"}
            >
              {copiedLineage === meta.config.task_id ? <Check /> : <Copy />}
            </button>
          </div>
        </div>
      )}
      <BaseOutputView meta={meta} kind={kind} zh={zh} />
      {kind === "backtest" && meta.task_key === "backtest" && (
        <Suspense
          fallback={
            <div className="research-loading">
              <LoaderCircle className="spin" />
            </div>
          }
        >
          <BacktestView meta={meta} zh={zh} remoteIp={remoteIp} />
        </Suspense>
      )}
    </>
  );
}

const iconFor = (kind: Kind) =>
  kind === "analysis" ? (
    <Sparkles />
  ) : kind === "backtest" ? (
    <TrendingUp />
  ) : kind === "train" ? (
    <BrainCircuit />
  ) : kind === "predict" ? (
    <BarChart3 />
  ) : (
    <Database />
  );
function Kpis({
  items,
}: {
  items: { label: string; value: React.ReactNode; hint?: string }[];
}) {
  return (
    <div className="artifact-kpis">
      {items.map((item) => (
        <article key={item.label}>
          <small>{item.label}</small>
          <strong>{item.value}</strong>
          {item.hint && <span>{item.hint}</span>}
        </article>
      ))}
    </div>
  );
}

function BaseOutputView({
  meta,
  kind,
  zh,
}: {
  meta: Meta;
  kind: Kind;
  zh: boolean;
}) {
  const count =
    kind === "train"
      ? meta.train_rows
      : kind === "backtest"
        ? meta.days
        : meta.rows;
  const countLabel =
    kind === "train"
      ? zh
        ? "训练行数"
        : "TRAIN ROWS"
      : kind === "backtest"
        ? zh
          ? "回测天数"
          : "DAYS"
        : zh
          ? "数据行数"
          : "ROWS";
  const paths =
    kind === "etl"
      ? [["output_file", meta.output_file]]
      : kind === "analysis"
        ? [["result_file", meta.result_file]]
        : kind === "train"
          ? [["model_file", meta.model_file]]
          : kind === "predict"
            ? [["predictions_file", meta.predictions_file]]
            : [
                ["daily_file", meta.daily_file],
                ["summary_file", meta.summary_file],
              ];
  const columns =
    kind === "etl"
      ? [
          [zh ? "特征列" : "Feature columns", meta.feature_columns],
          [zh ? "标签列" : "Label columns", meta.label_columns],
        ]
      : kind === "train" || kind === "predict"
        ? [
            [zh ? "特征列" : "Feature columns", meta.feature_columns],
            [zh ? "目标列" : "Target columns", meta.target_columns],
          ]
        : [];
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          { label: countLabel, value: fmt(count, 0) },
          ...(kind === "train"
            ? [
                {
                  label: zh ? "模型名称" : "MODEL",
                  value: meta.model_name || "—",
                },
              ]
            : []),
          ...(kind === "etl" || kind === "predict" || kind === "backtest"
            ? [
                {
                  label: zh ? "开始日期" : "START",
                  value: meta.date_range?.start || "—",
                },
                {
                  label: zh ? "结束日期" : "END",
                  value: meta.date_range?.end || "—",
                },
              ]
            : []),
          {
            label: zh ? "产物数" : "ARTIFACTS",
            value: fmt(Object.keys(meta.artifacts || {}).length, 0),
          },
        ]}
      />
      {columns.map(
        ([title, values]) =>
          Array.isArray(values) &&
          values.length > 0 && (
            <section className="viz-card" key={String(title)}>
              <header>
                <div>
                  <small>COLUMNS</small>
                  <h3>{title}</h3>
                </div>
                <span>{values.length}</span>
              </header>
              <div className="base-column-list">
                {values.map((value) => (
                  <code key={value}>{value}</code>
                ))}
              </div>
            </section>
          ),
      )}
      {kind === "analysis" &&
        Object.entries(meta.scores || {}).map(([metric, values]) => (
          <section className="viz-card wide" key={metric}>
            <header>
              <div>
                <small>SCORES</small>
                <h3>{metric}</h3>
              </div>
              <span>{Object.keys(values).length}</span>
            </header>
            <div className="base-value-list">
              {Object.entries(values)
                .slice(0, 20)
                .map(([subject, value]) => (
                  <div key={subject}>
                    <code>{subject}</code>
                    <strong>{fmt(value, 4)}</strong>
                  </div>
                ))}
            </div>
            {Object.keys(values).length > 20 && (
              <small>
                {zh
                  ? "仅显示前 20 项；完整结果见产物文件"
                  : "Showing 20 entries; see the artifact for full results"}
              </small>
            )}
          </section>
        ))}
      {kind === "train" && Object.keys(meta.metrics || {}).length > 0 && (
        <section className="viz-card wide">
          <header>
            <div>
              <small>METRICS</small>
              <h3>{zh ? "训练指标" : "Training metrics"}</h3>
            </div>
          </header>
          <div className="base-value-list">
            {Object.entries(meta.metrics || {}).map(([name, value]) => (
              <div key={name}>
                <code>{name}</code>
                <strong>{fmt(value, 4)}</strong>
              </div>
            ))}
          </div>
        </section>
      )}
      {kind === "train" && Object.keys(meta.parameters || {}).length > 0 && (
        <section className="viz-card wide">
          <header>
            <div>
              <small>PARAMETERS</small>
              <h3>{zh ? "生效参数" : "Effective parameters"}</h3>
            </div>
          </header>
          <div className="base-value-list">
            {Object.entries(meta.parameters || {}).map(([name, value]) => (
              <div key={name}>
                <code>{name}</code>
                <strong>
                  {typeof value === "string" ? value : JSON.stringify(value)}
                </strong>
              </div>
            ))}
          </div>
        </section>
      )}
      <section className="viz-card wide">
        <header>
          <div>
            <small>OUTPUT</small>
            <h3>{zh ? "输出文件" : "Output files"}</h3>
          </div>
        </header>
        <div className="artifact-files">
          {paths.map(
            ([name, path]) =>
              path && (
                <div key={name}>
                  <FileSpreadsheet />
                  <span>
                    <strong>{name}</strong>
                    <code>{path}</code>
                  </span>
                </div>
              ),
          )}
        </div>
        {kind === "etl" && meta.config.input_dir && (
          <small>
            {zh ? "输入目录" : "Input directory"}:{" "}
            <code>{meta.config.input_dir}</code>
          </small>
        )}
      </section>
      <section className="viz-card wide">
        <header>
          <div>
            <small>ARTIFACTS</small>
            <h3>{zh ? "产物清单" : "Artifacts"}</h3>
          </div>
        </header>
        <ArtifactFiles meta={meta} />
      </section>
    </div>
  );
}

function ArtifactFiles({
  meta,
  exclude = [],
}: {
  meta: Meta;
  exclude?: string[];
}) {
  return (
    <div className="artifact-files">
      {Object.entries(meta.artifacts || {})
        .filter(([name]) => !exclude.includes(name))
        .map(([name, file]) => (
          <div key={name}>
            <FileSpreadsheet />
            <span>
              <strong>{name}</strong>
              <code>{file.path}</code>
            </span>
            <em>{formatBytes(file.bytes, false)}</em>
          </div>
        ))}
    </div>
  );
}
