import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
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
import type {
  FeatureGroupConfig,
  ResearchArtifact,
  ResearchKind,
  ResearchPageId,
  ResearchRow,
} from "./types";

const BacktestView = lazy(() =>
  import("./backtest/BacktestView").then((module) => ({
    default: module.BacktestView,
  })),
);

type Meta = ResearchArtifact;
type Row = ResearchRow;
type Kind = ResearchKind;

const copy = {
  analysis: {
    zh: ["因子分析", "比较 IC、RankIC、分层收益与稳定性"],
    en: [
      "Factor analysis",
      "Compare IC, RankIC, quantile returns, and stability",
    ],
  },
  backtest: {
    zh: ["回测分析", "收益曲线、绩效指标与每日持仓检查"],
    en: [
      "Backtest analytics",
      "Equity curves, performance metrics, and daily holdings",
    ],
  },
  etl: {
    zh: ["ETL 数据集", "管理特征数据版本、覆盖范围与字段结构"],
    en: [
      "ETL datasets",
      "Manage feature dataset versions, coverage, and schema",
    ],
  },
  training: {
    zh: ["模型管理", "追踪训练实验、过程指标与验证效果"],
    en: [
      "Model registry",
      "Track experiments, training metrics, and validation quality",
    ],
  },
  predict: {
    zh: ["预测结果", "检查模型输出、样本覆盖及上游训练版本"],
    en: [
      "Predictions",
      "Inspect model outputs, coverage, and upstream training versions",
    ],
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
const pct = (value: unknown) =>
  Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : "—";
async function readAllCsv(path: string, remoteIp?: string) {
  const rows: unknown[][] = [];
  let columns: string[] = [];
  for (let offset = 0; offset < 5000; offset += 200) {
    const page = await previewWorkspaceFile(path, offset, 200, remoteIp);
    columns = page.columns || columns;
    rows.push(...(page.rows || []));
    if (!page.has_more) break;
  }
  return rows.map((row) =>
    Object.fromEntries(
      columns.map((column, index) => [column, String(row[index] ?? "")]),
    ),
  );
}

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
              return {
                ...(preview.data as Meta),
                _path: entry.path,
                _modified: entry.modified_at,
              };
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
      tasks.some((task) => task.task_id === initialSelectedId)
    )
      setSelectedId(initialSelectedId);
    else if (!tasks.some((task) => task.task_id === selectedId))
      setSelectedId("");
  }, [tasks, selectedId, initialSelectedId]);
  useEffect(() => {
    onOptionsChange?.(
      tasks.map((task) => ({
        value: task.task_id,
        label: task.task_id,
        detail: task.task_name || kind,
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
  const selected = tasks.find((task) => task.task_id === selectedId);
  const visible = tasks.filter((task) =>
    `${task.task_id} ${task.task_name}`
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
                  className={`${selectedId === task.task_id ? "active" : ""} ${checked[task._path] ? "checked" : ""}`}
                  key={task.task_id}
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
                      aria-label={`${zh ? "选择" : "Select"} ${task.task_id}`}
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
                        : (setSelectedId(task.task_id),
                          onSelected?.(task.task_id))
                    }
                  >
                    <span
                      className={`run-item-avatar rail-avatar run-kind-${kind}`}
                    >
                      {String(task.task_name || kind)
                        .trim()
                        .slice(0, 1)
                        .toUpperCase()}
                    </span>
                    <span className="rail-item-copy">
                      <strong>{task.task_name || kind}</strong>
                      <code>{task.task_id}</code>
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
        <RailResizer min={250} max={460} className="context-resizer" />
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
            <span>{contextMenu.task.task_id}</span>
            <small>{contextMenu.task.task_name || kind}</small>
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
                <code key={task._path}>{task.task_id}</code>
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
  const [csv, setCsv] = useState<Record<string, Row[]>>({});
  const [loading, setLoading] = useState(true);
  const [copiedLineage, setCopiedLineage] = useState("");
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const artifacts = meta.artifacts || {};
    const wanted =
      kind === "analysis"
        ? ["result", "quantiles"]
        : kind === "backtest"
          ? []
          : kind === "training"
            ? ["evaluation_history"]
            : kind === "etl"
              ? ["statistics"]
              : [];
    Promise.all(
      wanted
        .filter((key) => artifacts[key])
        .map(
          async (key) =>
            [
              key,
              await readAllCsv(`${meta._path}/${artifacts[key]}`, remoteIp),
            ] as const,
        ),
    )
      .then((items) => alive && setCsv(Object.fromEntries(items)))
      .finally(() => alive && setLoading(false));
    if (!wanted.length) setLoading(false);
    return () => {
      alive = false;
    };
  }, [meta.task_id, meta._path, meta.artifacts, remoteIp, kind]);
  const upstream =
    kind === "analysis"
      ? meta.source?.etl_task_id
      : kind === "backtest"
        ? meta.source?.prediction_task_id
        : kind === "training"
          ? meta.source?.etl_task_id
          : kind === "predict"
            ? meta.source?.training_task_id
            : null;
  const upstreamPage: ResearchPageId | null =
    kind === "analysis" || kind === "training"
      ? "etl"
      : kind === "backtest"
        ? "predict"
        : kind === "predict"
          ? "training"
          : null;
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
              <small>{meta.task_name || kind}</small>
              <h2>{meta.task_id}</h2>
            </div>
          </div>
          <span className="ready-badge">
            <CheckCircle2 />
            {zh ? "产物就绪" : "Artifacts ready"}
          </span>
        </header>
      }
      {upstream && upstreamPage && (
        <div className="lineage-strip">
          <span>
            <GitBranch />
            {zh ? "数据血缘" : "LINEAGE"}
          </span>
          <div className="lineage-node">
            <button
              className="lineage-link"
              onClick={() => onNavigate(upstreamPage, upstream)}
              title={zh ? "打开上游任务" : "Open upstream task"}
            >
              <em>{upstreamPage.toUpperCase()}</em>
              <code>{upstream}</code>
              <ArrowRight />
            </button>
            <button
              className="lineage-copy"
              onClick={() => void copyLineageId(upstream)}
              aria-label={zh ? "复制上游 Task ID" : "Copy upstream task ID"}
              title={
                copiedLineage === upstream
                  ? zh
                    ? "已复制"
                    : "Copied"
                  : zh
                    ? "复制 Task ID"
                    : "Copy task ID"
              }
            >
              {copiedLineage === upstream ? <Check /> : <Copy />}
            </button>
          </div>
          <i />
          <div className="lineage-node current">
            <strong>
              <em>{kind.toUpperCase()}</em>
              <code>{meta.task_id}</code>
            </strong>
            <button
              className="lineage-copy"
              onClick={() => void copyLineageId(meta.task_id)}
              aria-label={zh ? "复制当前 Task ID" : "Copy current task ID"}
              title={
                copiedLineage === meta.task_id
                  ? zh
                    ? "已复制"
                    : "Copied"
                  : zh
                    ? "复制 Task ID"
                    : "Copy task ID"
              }
            >
              {copiedLineage === meta.task_id ? <Check /> : <Copy />}
            </button>
          </div>
        </div>
      )}
      {loading ? (
        <div className="research-loading">
          <LoaderCircle className="spin" />
        </div>
      ) : kind === "analysis" ? (
        <AnalysisView
          meta={meta}
          result={csv.result || []}
          quantiles={csv.quantiles || []}
          zh={zh}
        />
      ) : kind === "backtest" ? (
        <Suspense
          fallback={
            <div className="research-loading">
              <LoaderCircle className="spin" />
            </div>
          }
        >
          <BacktestView meta={meta} zh={zh} remoteIp={remoteIp} />
        </Suspense>
      ) : kind === "training" ? (
        <TrainingView
          meta={meta}
          history={csv.evaluation_history || []}
          zh={zh}
        />
      ) : kind === "etl" ? (
        <EtlView meta={meta} statistics={csv.statistics || []} zh={zh} />
      ) : (
        <PredictView meta={meta} zh={zh} />
      )}
    </>
  );
}

const iconFor = (kind: Kind) =>
  kind === "analysis" ? (
    <Sparkles />
  ) : kind === "backtest" ? (
    <TrendingUp />
  ) : kind === "training" ? (
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

function AnalysisView({
  meta,
  result,
  quantiles,
  zh,
}: {
  meta: Meta;
  result: Row[];
  quantiles: Row[];
  zh: boolean;
}) {
  const [label, setLabel] = useState("label_1d");
  const filtered = result
    .filter((row) => row.label === label)
    .sort(
      (a, b) =>
        Math.abs(Number(b.rankic_mean)) - Math.abs(Number(a.rankic_mean)),
    );
  const top = filtered.slice(0, 100);
  const labels = Array.from(new Set(result.map((row) => row.label)));
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          {
            label: zh ? "因子数" : "FACTORS",
            value: fmt(meta.feature_count, 0),
          },
          { label: zh ? "分析样本" : "SAMPLES", value: fmt(meta.rows, 0) },
          {
            label: zh ? "有效交易日" : "TRADING DAYS",
            value: fmt(filtered[0]?.valid_days, 0),
          },
          {
            label: zh ? "分组数" : "QUANTILES",
            value: fmt(meta.config?.quantiles, 0),
          },
        ]}
      />
      <section className="viz-card wide factor-ranking-bars">
        <header>
          <div>
            <small>FACTOR SIGNAL</small>
            <h3>
              {zh
                ? "RankIC 绝对值 Top 100"
                : "Top 100 factors by absolute RankIC"}
            </h3>
          </div>
          <select value={label} onChange={(e) => setLabel(e.target.value)}>
            {labels.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </header>
        <BarList rows={top} name="factor" value="rankic_mean" />
      </section>
      <section className="viz-card">
        <header>
          <div>
            <small>QUANTILE RETURN</small>
            <h3>{zh ? "最佳因子分层收益" : "Top factor quantile return"}</h3>
          </div>
        </header>
        <BarList
          rows={quantiles.filter(
            (row) => row.factor === top[0]?.factor && row.label === label,
          )}
          name="quantile"
          value="mean_return"
          percent
        />
      </section>
      <section className="viz-card">
        <header>
          <div>
            <small>FACTOR TABLE</small>
            <h3>{zh ? "因子排名 Top 100" : "Top 100 factor ranking"}</h3>
          </div>
        </header>
        <MiniTable
          rows={top}
          columns={[
            "factor",
            "rankic_mean",
            "rankicir",
            "coverage",
            "direction",
          ]}
        />
      </section>
    </div>
  );
}

function TrainingView({
  meta,
  history,
  zh,
}: {
  meta: Meta;
  history: Row[];
  zh: boolean;
}) {
  const metricKeys = Object.keys(history[0] || {}).filter(
    (key) =>
      key !== "iteration" &&
      history.some((row) => Number.isFinite(Number(row[key]))),
  );
  const series = metricKeys.map((key) => ({
    key,
    label: key.replaceAll("_", " "),
  }));
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          {
            label: zh ? "算法" : "ALGORITHM",
            value: meta.model?.library || "—",
            hint: meta.model?.library_version,
          },
          {
            label: zh ? "最佳迭代" : "BEST ITERATION",
            value: fmt(meta.model?.best_iteration, 0),
          },
          {
            label: "VALIDATION IC",
            value: fmt(meta.validation_metrics?.ic_mean, 4),
          },
          {
            label: "RANK IC",
            value: fmt(meta.validation_metrics?.rankic_mean, 4),
          },
        ]}
      />
      <section className="viz-card wide training-curve-card">
        <header>
          <div>
            <small>
              TRAINING PROCESS · {fmt(history.length, 0)}{" "}
              {zh ? "次迭代" : "ITERATIONS"}
            </small>
            <h3>{zh ? "训练过程指标" : "Training metrics over time"}</h3>
          </div>
        </header>
        <LineChart rows={history} series={series} xKey="iteration" />
      </section>
      <section className="viz-card training-metrics-card">
        <header>
          <div>
            <small>METRIC CHANGES</small>
            <h3>{zh ? "过程数字变化" : "Metric changes"}</h3>
          </div>
        </header>
        <MetricChanges rows={history} keys={metricKeys} zh={zh} />
      </section>
      <section className="viz-card">
        <header>
          <div>
            <small>MODEL ARTIFACT</small>
            <h3>{zh ? "模型版本" : "Model version"}</h3>
          </div>
        </header>
        <ArtifactFiles meta={meta} exclude={["feature_importance"]} />
      </section>
    </div>
  );
}

type FeatureGroup = { name: string; description?: string; features: string[] };

function featureGroupsOf(
  meta: Meta,
  features: string[],
  zh: boolean,
): FeatureGroup[] {
  const configured = meta.feature_schema?.groups ?? meta.feature_groups;
  const groups: FeatureGroup[] = [];
  if (Array.isArray(configured)) {
    for (const [index, item] of configured.entries()) {
      if (!item || typeof item !== "object") continue;
      const group = item as FeatureGroupConfig;
      const columns = Array.isArray(group.features)
        ? group.features
        : Array.isArray(group.columns)
          ? group.columns
          : [];
      groups.push({
        name: String(
          group.name || group.label || `${zh ? "分组" : "Group"} ${index + 1}`,
        ),
        description: group.description ? String(group.description) : undefined,
        features: columns.map(String),
      });
    }
  } else if (configured && typeof configured === "object") {
    for (const [name, columns] of Object.entries(configured)) {
      if (Array.isArray(columns))
        groups.push({ name, features: columns.map(String) });
    }
  }
  const featureSet = new Set(features);
  const assigned = new Set<string>();
  const normalized = groups
    .map((group) => ({
      ...group,
      features: group.features.filter((feature) => {
        if (!featureSet.has(feature) || assigned.has(feature)) return false;
        assigned.add(feature);
        return true;
      }),
    }))
    .filter((group) => group.features.length);
  const unassigned = features.filter((feature) => !assigned.has(feature));
  if (unassigned.length)
    normalized.push({
      name: normalized.length
        ? zh
          ? "其他特征"
          : "Other features"
        : zh
          ? "全部特征"
          : "All features",
      features: unassigned,
    });
  return normalized;
}

function EtlView({
  meta,
  statistics,
  zh,
}: {
  meta: Meta;
  statistics: Row[];
  zh: boolean;
}) {
  const features = (meta.feature_columns || []) as string[];
  const [featureQuery, setFeatureQuery] = useState("");
  const featureGroups = featureGroupsOf(meta, features, zh);
  const query = featureQuery.trim().toLocaleLowerCase();
  const visibleGroups = featureGroups
    .map((group) => ({
      ...group,
      features: group.features.filter((feature) =>
        `${group.name} ${feature}`.toLocaleLowerCase().includes(query),
      ),
    }))
    .filter((group) => group.features.length);
  const featureSet = new Set(features);
  const labelColumns = new Set<string>([
    ...Object.values(meta.labels || {})
      .filter(Array.isArray)
      .flat()
      .map(String),
    ...((meta.label_columns || []) as string[]),
  ]);
  const featureStats = statistics.filter((row) => featureSet.has(row.column));
  const labelStats = statistics.filter((row) => labelColumns.has(row.column));
  const minimumFinite = (rows: Row[]) => {
    const values = rows
      .map((row) => Number(row.finite_rate))
      .filter(Number.isFinite);
    return values.length ? Math.min(...values) : NaN;
  };
  const relevantStats = statistics.filter(
    (row) => featureSet.has(row.column) || labelColumns.has(row.column),
  );
  const worst = [...(relevantStats.length ? relevantStats : statistics)]
    .sort((left, right) => Number(right.null_rate) - Number(left.null_rate))
    .slice(0, 5);
  const labelHelp: Record<string, string> = zh
    ? {
        raw: "未来 1–5 个交易日复权收益",
        csz: "截面去极值后标准化",
        rank: "当日截面百分位排名",
        valid: "对应期限标签是否有效",
      }
    : {
        raw: "Adjusted 1–5 trading-day returns",
        csz: "Cross-sectional winsorized z-score",
        rank: "Daily cross-sectional percentile rank",
        valid: "Whether the horizon label is valid",
      };
  const configuredTitle = meta.feature_schema?.title;
  const schemaTitle =
    typeof configuredTitle === "object"
      ? configuredTitle[zh ? "zh" : "en"]
      : configuredTitle || (zh ? "特征结构" : "Feature schema");
  return (
    <div className="artifact-content etl-content">
      <Kpis
        items={[
          { label: zh ? "数据行数" : "ROWS", value: fmt(meta.rows, 0) },
          { label: zh ? "股票数" : "SYMBOLS", value: fmt(meta.symbols, 0) },
          {
            label: zh ? "特征数" : "FEATURES",
            value: fmt(features.length, 0),
            hint:
              featureGroups.length > 1
                ? `${featureGroups.length} ${zh ? "个分组" : "groups"}`
                : undefined,
          },
          {
            label: zh ? "数据范围" : "DATE RANGE",
            value: `${meta.date_range?.start || "—"} — ${meta.date_range?.end || "—"}`,
          },
        ]}
      />
      <section className="viz-card wide etl-feature-card">
        <header>
          <div>
            <small>FEATURE SCHEMA</small>
            <h3>{schemaTitle}</h3>
          </div>
          <label className="feature-search">
            <Search />
            <input
              value={featureQuery}
              onChange={(event) => setFeatureQuery(event.target.value)}
              placeholder={zh ? "搜索特征" : "Search features"}
            />
          </label>
        </header>
        <div className="feature-catalog generic">
          {visibleGroups.map((group) => (
            <section key={group.name}>
              <header>
                <span>{group.name}</span>
                <em>{group.features.length}</em>
              </header>
              {group.description && <p>{group.description}</p>}
              <div className="base-features">
                {group.features.map((feature) => (
                  <code key={feature} title={meta.schema?.[feature]}>
                    {feature}
                  </code>
                ))}
              </div>
            </section>
          ))}
          {!visibleGroups.length && (
            <div className="feature-empty">
              {features.length
                ? zh
                  ? "没有匹配的特征"
                  : "No matching features"
                : zh
                  ? "该版本没有声明特征字段"
                  : "No feature columns declared"}
            </div>
          )}
        </div>
      </section>
      <section className="viz-card etl-label-card">
        <header>
          <div>
            <small>LABELS</small>
            <h3>{zh ? "监督目标" : "Learning targets"}</h3>
          </div>
          <span className="card-count">
            {
              Object.values(meta.labels || {})
                .filter(Array.isArray)
                .flat().length
            }
          </span>
        </header>
        <div className="label-groups">
          {Object.entries(meta.labels || {})
            .filter(([, value]) => Array.isArray(value))
            .map(([key, value]) => (
              <div key={key}>
                <span>
                  <strong>{key}</strong>
                  <small>{labelHelp[key]}</small>
                </span>
                <div>
                  {(value as string[]).map((label) => (
                    <code key={label}>{label}</code>
                  ))}
                </div>
              </div>
            ))}
        </div>
      </section>
      <section className="viz-card etl-quality-card">
        <header>
          <div>
            <small>DATA QUALITY</small>
            <h3>{zh ? "完整率与缺失字段" : "Coverage and missing values"}</h3>
          </div>
        </header>
        {statistics.length ? (
          <>
            <div className="quality-summary">
              <article>
                <small>{zh ? "特征最低完整率" : "MIN FEATURE COVERAGE"}</small>
                <strong>{pct(minimumFinite(featureStats))}</strong>
              </article>
              <article>
                <small>{zh ? "标签最低完整率" : "MIN LABEL COVERAGE"}</small>
                <strong>{pct(minimumFinite(labelStats))}</strong>
              </article>
            </div>
            <div className="quality-list">
              {worst.map((row) => (
                <div key={row.column}>
                  <code title={row.column}>{row.column}</code>
                  <span>
                    <i
                      style={{
                        width: `${Math.max(2, Number(row.finite_rate) * 100)}%`,
                      }}
                    />
                  </span>
                  <strong>{pct(row.finite_rate)}</strong>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="quality-empty">
            {zh
              ? "该版本没有统计文件"
              : "No statistics artifact for this version"}
          </div>
        )}
      </section>
      <section className="viz-card wide etl-artifacts-card">
        <header>
          <div>
            <small>ARTIFACTS</small>
            <h3>{zh ? "数据文件" : "Dataset files"}</h3>
          </div>
          <span className="card-count">
            {Object.keys(meta.artifact_integrity || {}).length}
          </span>
        </header>
        <ArtifactFiles meta={meta} />
      </section>
    </div>
  );
}
function PredictView({ meta, zh }: { meta: Meta; zh: boolean }) {
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          { label: zh ? "预测行数" : "PREDICTIONS", value: fmt(meta.rows, 0) },
          { label: zh ? "目标" : "TARGET", value: meta.model_target },
          { label: zh ? "开始日期" : "START", value: meta.date_range?.start },
          { label: zh ? "结束日期" : "END", value: meta.date_range?.end },
        ]}
      />
      <section className="viz-card wide prediction-overview">
        <div>
          <BarChart3 />
          <h3>
            {zh ? "截面预测数据已就绪" : "Cross-sectional predictions ready"}
          </h3>
          <p>
            {zh
              ? "预测产物以 Parquet 保存，包含每日全市场评分、真实收益和指数权重，可继续用于回测。"
              : "The Parquet artifact contains daily market-wide scores, realized returns, and index weights for downstream backtests."}
          </p>
        </div>
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
      {Object.entries(meta.artifact_integrity || {})
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
function MiniTable({ rows, columns }: { rows: Row[]; columns: string[] }) {
  return (
    <div className="mini-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>
                  {Number.isFinite(Number(row[column])) && row[column] !== ""
                    ? fmt(row[column], 4)
                    : row[column]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function BarList({
  rows,
  name,
  value,
  percent = false,
}: {
  rows: Row[];
  name: string;
  value: string;
  percent?: boolean;
}) {
  const max = Math.max(
    ...rows.map((row) => Math.abs(Number(row[value]))),
    0.000001,
  );
  return (
    <div className="bar-list">
      {rows.map((row, index) => (
        <div key={`${row[name]}-${index}`}>
          <code>{row[name]}</code>
          <span>
            <i
              className={Number(row[value]) < 0 ? "negative" : ""}
              style={{
                width: `${Math.max(2, (Math.abs(Number(row[value])) / max) * 100)}%`,
              }}
            />
          </span>
          <strong>{percent ? pct(row[value]) : fmt(row[value], 4)}</strong>
        </div>
      ))}
    </div>
  );
}
type ChartSeries = {
  key: string;
  label?: string;
  color?: string;
  dashed?: boolean;
};
const chartColors = [
  "var(--accent)",
  "#3569db",
  "#a15bd8",
  "#df8a2f",
  "#d94f70",
  "#16a3a5",
];

function MetricChanges({
  rows,
  keys,
  zh,
}: {
  rows: Row[];
  keys: string[];
  zh: boolean;
}) {
  if (!rows.length || !keys.length)
    return <div className="chart-empty">NO METRIC DATA</div>;
  return (
    <div className="metric-changes">
      {keys.map((key, index) => {
        const values = rows
          .map((row) => Number(row[key]))
          .filter(Number.isFinite);
        const first = values[0];
        const latest = values.at(-1) ?? first;
        const best = Math.min(...values);
        const change = latest - first;
        return (
          <article key={key}>
            <header>
              <i
                style={{ background: chartColors[index % chartColors.length] }}
              />
              <strong>{key.replaceAll("_", " ")}</strong>
            </header>
            <div>
              <span>
                <small>{zh ? "起始" : "START"}</small>
                <b>{fmt(first, 6)}</b>
              </span>
              <span>
                <small>{zh ? "最优" : "BEST"}</small>
                <b>{fmt(best, 6)}</b>
              </span>
              <span>
                <small>{zh ? "当前" : "LATEST"}</small>
                <b>{fmt(latest, 6)}</b>
              </span>
            </div>
            <footer className={change <= 0 ? "improved" : "worsened"}>
              {zh ? "累计变化" : "TOTAL CHANGE"}
              <em>
                {change > 0 ? "+" : ""}
                {fmt(change, 6)}
              </em>
            </footer>
          </article>
        );
      })}
    </div>
  );
}

function LineChart({
  rows,
  value,
  benchmark,
  series: requestedSeries,
  xKey,
}: {
  rows: Row[];
  value?: string;
  benchmark?: string;
  series?: ChartSeries[];
  xKey?: string;
}) {
  const fallback: ChartSeries[] = value
    ? [
        { key: value, label: value },
        ...(benchmark
          ? [{ key: benchmark, label: benchmark, dashed: true }]
          : []),
      ]
    : [];
  const definitions = (
    requestedSeries?.length ? requestedSeries : fallback
  ).map((item, index) => ({
    ...item,
    color: item.color || chartColors[index % chartColors.length],
  }));
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [chartWidth, setChartWidth] = useState(800);
  const stageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const resize = new ResizeObserver(([entry]) =>
      setChartWidth(Math.max(320, Math.round(entry.contentRect.width))),
    );
    resize.observe(stage);
    return () => resize.disconnect();
  }, []);
  const all = definitions.flatMap((item) =>
    rows.map((row) => Number(row[item.key])).filter(Number.isFinite),
  );
  if (!all.length) return <div className="chart-empty">NO SERIES DATA</div>;
  const chartHeight = Math.max(
    260,
    Math.min(420, Math.round(chartWidth / 3.8)),
  );
  const left = 62,
    right = chartWidth - 16,
    top = 18,
    bottom = chartHeight - 26;
  const minValue = Math.min(...all),
    maxValue = Math.max(...all);
  const padding = (maxValue - minValue || Math.abs(maxValue) || 1) * 0.08;
  const min = minValue - padding,
    max = maxValue + padding,
    range = max - min || 1;
  const x = (index: number) =>
    left + (index / Math.max(1, rows.length - 1)) * (right - left);
  const y = (number: number) =>
    bottom - ((number - min) / range) * (bottom - top);
  const path = (key: string) =>
    rows
      .map((row, index) => ({ value: Number(row[key]), index }))
      .filter((point) => Number.isFinite(point.value))
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${x(point.index)},${y(point.value)}`,
      )
      .join(" ");
  const yTicks = Array.from(
    { length: 5 },
    (_, index) => max - (index * range) / 4,
  );
  const activeIndex = hoverIndex ?? rows.length - 1;
  const activeX = x(activeIndex);
  const resolvedXKey =
    xKey || (rows[activeIndex]?.trade_date ? "trade_date" : "iteration");
  const xValue = rows[activeIndex]?.[resolvedXKey];
  const move = (clientX: number, target: SVGSVGElement) => {
    const bounds = target.getBoundingClientRect();
    const svgX = ((clientX - bounds.left) / bounds.width) * chartWidth;
    setHoverIndex(
      Math.max(
        0,
        Math.min(
          rows.length - 1,
          Math.round(
            ((svgX - left) / (right - left)) * Math.max(1, rows.length - 1),
          ),
        ),
      ),
    );
  };
  return (
    <div
      className="line-chart interactive-chart"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          setHoverIndex(
            Math.max(
              0,
              Math.min(
                rows.length - 1,
                activeIndex + (event.key === "ArrowRight" ? 1 : -1),
              ),
            ),
          );
        }
      }}
      onBlur={() => setHoverIndex(null)}
    >
      <div className="chart-legend">
        {definitions.map((item) => (
          <span key={item.key}>
            <i style={{ background: item.color }} />
            {item.label || item.key}
          </span>
        ))}
      </div>
      <div className="chart-stage" ref={stageRef}>
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          preserveAspectRatio="none"
          style={{ height: chartHeight }}
          onPointerMove={(event) => move(event.clientX, event.currentTarget)}
          onPointerLeave={() => setHoverIndex(null)}
        >
          {yTicks.map((tick) => (
            <g key={tick}>
              <line
                x1={left}
                y1={y(tick)}
                x2={right}
                y2={y(tick)}
                className="chart-grid"
              />
              <text x={left - 9} y={y(tick) + 3} className="chart-y-label">
                {fmt(tick, 5)}
              </text>
            </g>
          ))}
          <line
            x1={left}
            y1={bottom}
            x2={right}
            y2={bottom}
            className="chart-axis"
          />
          {definitions.map((item) => (
            <path
              key={item.key}
              d={path(item.key)}
              className="chart-series"
              style={{
                stroke: item.color,
                strokeDasharray: item.dashed ? "6 5" : undefined,
              }}
            />
          ))}
          {hoverIndex !== null && (
            <>
              <line
                x1={activeX}
                y1={top}
                x2={activeX}
                y2={bottom}
                className="chart-crosshair"
              />
              {definitions.map((item) => {
                const number = Number(rows[activeIndex]?.[item.key]);
                return Number.isFinite(number) ? (
                  <circle
                    key={item.key}
                    cx={activeX}
                    cy={y(number)}
                    r="4"
                    style={{ stroke: item.color }}
                    className="chart-point"
                  />
                ) : null;
              })}
            </>
          )}
          <rect
            x={left}
            y={top}
            width={right - left}
            height={bottom - top}
            className="chart-hit-area"
          />
        </svg>
        {hoverIndex !== null && (
          <div
            className={`chart-tooltip ${activeX > chartWidth * 0.72 ? "align-right" : ""}`}
            style={{ left: `${(activeX / chartWidth) * 100}%` }}
          >
            <strong>
              <span>{resolvedXKey}</span>
              <b>{xValue}</b>
            </strong>
            {definitions.map((item) => (
              <span key={item.key}>
                <i style={{ background: item.color }} />
                {item.label || item.key}
                <b>{fmt(rows[activeIndex]?.[item.key], 7)}</b>
              </span>
            ))}
          </div>
        )}
      </div>
      <footer>
        <span>{rows[0]?.[resolvedXKey]}</span>
        <strong>
          {hoverIndex === null
            ? definitions.length > 1
              ? `${definitions.length} SERIES`
              : fmt(rows.at(-1)?.[definitions[0].key], 4)
            : `${resolvedXKey}: ${xValue}`}
        </strong>
        <span>{rows.at(-1)?.[resolvedXKey]}</span>
      </footer>
    </div>
  );
}
