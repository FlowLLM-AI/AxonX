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
  GitCompareArrows,
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
  listTaskRuns,
  previewWorkspaceFile,
} from "../workspace/api";
import { formatBytes } from "../../shared/lib/format";
import { RailResizer } from "../../shared/ui/RailResizer";
import type { ContextOption } from "../../app/types";
import { useTranslation } from "react-i18next";
import { resolvedLocale } from "../../i18n";
import type {
  ResearchArtifact,
  ResearchKind,
  ResearchPageId,
  TrainingCurveData,
} from "./types";

const BacktestView = lazy(() =>
  import("./backtest/BacktestView").then((module) => ({
    default: module.BacktestView,
  })),
);
const TrainingCurveChart = lazy(() =>
  import("./TrainingCurveChart").then((module) => ({
    default: module.TrainingCurveChart,
  })),
);

type Meta = ResearchArtifact;
type Kind = ResearchKind;

const fmt = (value: unknown, digits = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (Math.abs(number) >= 1_000_000)
    return new Intl.NumberFormat(resolvedLocale(), {
      notation: "compact",
      maximumFractionDigits: 2,
    }).format(number);
  return number.toLocaleString(resolvedLocale(), {
    maximumFractionDigits: digits,
  });
};

function normalizeTrainingCurve(value: unknown): TrainingCurveData | undefined {
  if (!value || typeof value !== "object") return undefined;
  const curve = value as Partial<TrainingCurveData>;
  if (!Array.isArray(curve.x)) return undefined;
  return {
    x: curve.x,
    y_left: curve.y_left || {},
    y_right: curve.y_right || {},
  };
}

function useTasks(
  kind: Kind,
  remoteIp?: string,
  onConnection?: (online: boolean) => void,
) {
  const [tasks, setTasks] = useState<Meta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const load = useCallback(() => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    setTasks([]);
    listTaskRuns(kind, remoteIp)
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
                preview.kind !== "json" ||
                !preview.data ||
                typeof preview.data !== "object" ||
                Array.isArray(preview.data)
              ) {
                throw new Error(
                  (preview.kind === "json" && preview.parse_error) ||
                    "Invalid task metadata",
                );
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
                feature_columns: output.feature_columns,
                label_columns: output.label_columns,
                target_columns: output.target_columns,
                output_columns: output.output_columns,
                prediction_statistics: output.statistics,
                index_weight_columns: output.index_weight_columns,
                scores: output.scores,
                model_name: output.model_name,
                metrics: output.metrics,
                parameters: output.parameters,
                training_curve: normalizeTrainingCurve(output.training_curve),
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
        if (currentRequest !== requestId.current) return;
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
        if (currentRequest !== requestId.current) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection?.(false);
      })
      .finally(() => {
        if (currentRequest === requestId.current) setLoading(false);
      });
  }, [kind, onConnection, remoteIp]);
  useEffect(() => {
    load();
    return () => {
      requestId.current += 1;
    };
  }, [load]);
  return { tasks, loading, error, load };
}

export default function ResearchPage({
  kind,
  remoteIp,
  initialSelectedId,
  onSelected,
  onOptionsChange,
  onConnection,
  onNavigate,
}: {
  kind: Kind;
  remoteIp?: string;
  initialSelectedId?: string;
  onSelected?: (taskId: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage === "zh" ? "zh-CN" : "en-US";
  const labels = [
    t(`research.pages.${kind}.title`),
    t(`research.pages.${kind}.lead`),
  ];
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
            {t("research.refresh")}
          </button>
        )}
      </div>
      {error && (
        <div className="error-banner">
          <AlertTriangle />
          <div>
            <strong>{t("research.unable_to_load_artifacts")}</strong>
            <span>{error}</span>
          </div>
          <button type="button" onClick={load}>
            {t("research.retry")}
          </button>
        </div>
      )}
      {!error && (
        <div className="research-layout">
          <aside
            className={`run-index rail-panel ${selectionMode ? "selecting" : ""}`}
          >
            <header className="run-index-header rail-header">
              <div className="run-index-heading rail-heading">
                <small>TASK VERSIONS</small>
                <strong>{t("research.task_versions")}</strong>
              </div>
              <div className="run-index-tools">
                <em>{tasks.length}</em>
                <button
                  className="run-index-refresh rail-refresh"
                  aria-label={t("research.refresh")}
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
                placeholder={t("research.search_task_id")}
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
                        aria-label={`${t("research.select")} ${task.config.task_id}`}
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
                            ? new Date(task.created_at).toLocaleString(locale)
                            : t("research.metadata_unavailable")}
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
                  {t("research.selected")}
                </span>
                <button
                  onClick={() => {
                    setSelectionMode(false);
                    setChecked({});
                  }}
                >
                  {t("research.done")}
                </button>
                <button onClick={toggleVisible}>
                  {allVisibleSelected
                    ? t("research.deselect")
                    : t("research.select_all")}
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
                  {t("research.delete")}
                </button>
              </footer>
            )}
          </aside>
          <RailResizer min={180} max={460} className="context-resizer" />
          <main className="research-canvas">
            {loading ? (
              <div className="research-loading">
                <LoaderCircle className="spin" />
              </div>
            ) : selected ? (
              <ArtifactDetail
                kind={kind}
                meta={selected}
                remoteIp={remoteIp}
                onNavigate={onNavigate}
              />
            ) : (
              !loading && (
                <div className="empty-research">
                  <Database />
                  <strong>
                    {tasks.length
                      ? t("research.select_a_task_version")
                      : t("research.noKindTasks", { kind })}
                  </strong>
                  <span>
                    {tasks.length
                      ? t("research.its_data_and_artifacts_will")
                      : t("research.task_artifacts_will_appear_here")}
                  </span>
                </div>
              )
            )}
          </main>
        </div>
      )}
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
            {t("research.select")}
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
            {t("research.delete")}
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
              aria-label={t("research.cancel")}
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
                ? t("research.delete_selected_task_versions")
                : t("research.delete_this_task_version")}
            </h2>
            <div className="workspace-delete-list">
              {deleteTargets.slice(0, 6).map((task) => (
                <code key={task._path}>{task.config.task_id}</code>
              ))}
              {deleteTargets.length > 6 && (
                <span>+{deleteTargets.length - 6}</span>
              )}
            </div>
            <p>{t("research.the_task_directories_and_all")}</p>
            {deleteError && (
              <div className="inline-error">
                <strong>{t("research.delete_failed")}</strong>
                <span>{deleteError}</span>
              </div>
            )}
            <div>
              <button
                className="secondary-button"
                disabled={deleting}
                onClick={() => setDeleteTargets([])}
              >
                {t("research.cancel")}
              </button>
              <button
                className="danger-button"
                disabled={deleting}
                onClick={() => void confirmDelete()}
              >
                {deleting ? <LoaderCircle className="spin" /> : <Trash2 />}
                {deleting
                  ? t("research.deleting")
                  : `${t("research.delete")} (${deleteTargets.length})`}
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
  remoteIp,
  onNavigate,
}: {
  kind: Kind;
  meta: Meta;
  remoteIp?: string;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const { t } = useTranslation();
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
    page: pageByType[taskId.split("#")[0]] || ("runtime" as const),
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
            <div className="artifact-title">
              <small>{meta.task_key || kind}</small>
              <div className="artifact-title-row">
                <h2 title={meta.config.task_id}>{meta.config.task_id}</h2>
                <button
                  type="button"
                  className="artifact-id-copy"
                  onClick={() => void copyLineageId(meta.config.task_id)}
                  title={t("research.copy_task_id")}
                  aria-label={t("research.copy_task_id")}
                >
                  {copiedLineage === meta.config.task_id ? <Check /> : <Copy />}
                </button>
              </div>
            </div>
          </div>
          <div className="artifact-header-actions">
            {kind === "backtest" && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => onNavigate("compare", meta.config.task_id)}
              >
                <GitCompareArrows />
                {t("research.compare")}
              </button>
            )}
            <span className="ready-badge">
              <CheckCircle2 />
              {t("research.artifacts_ready")}
            </span>
          </div>
        </header>
      }
      {upstreams.length > 0 && (
        <div className="lineage-strip">
          <span>
            <GitBranch />
            {t("research.upstream_tasks")}
          </span>
          <div className="lineage-sources">
            {upstreams.map((upstream) => (
              <div className="lineage-node" key={upstream.taskId}>
                <button
                  className="lineage-link"
                  onClick={() => onNavigate(upstream.page, upstream.taskId)}
                  title={`${t("research.open_upstream_task")}: ${upstream.taskId}`}
                >
                  <em>{upstream.type.toUpperCase()}</em>
                  <code>{upstream.taskId}</code>
                  <ArrowRight />
                </button>
                <button
                  className="lineage-copy"
                  onClick={() => void copyLineageId(upstream.taskId)}
                  aria-label={t("research.copy_upstream_task_id")}
                >
                  {copiedLineage === upstream.taskId ? <Check /> : <Copy />}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      <BaseOutputView meta={meta} kind={kind} />
      {kind === "backtest" && (
        <Suspense
          fallback={
            <div className="research-loading">
              <LoaderCircle className="spin" />
            </div>
          }
        >
          <BacktestView meta={meta} remoteIp={remoteIp} />
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
    <div className={`artifact-kpis count-${Math.min(items.length, 4)}`}>
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

function AnalysisScores({
  scores,
}: {
  scores: Record<string, Record<string, number>>;
}) {
  const { t } = useTranslation();
  const [chosenMetric, setChosenMetric] = useState("");
  const [chosenLabel, setChosenLabel] = useState("");
  const groups = Object.entries(scores).map(([key, values]) => {
    const separator = key.indexOf("/");
    return {
      metric: separator < 0 ? key : key.slice(0, separator),
      label: separator < 0 ? "—" : key.slice(separator + 1),
      values,
    };
  });
  if (!groups.length) return null;
  const metrics = [...new Set(groups.map((group) => group.metric))];
  const metric = metrics.includes(chosenMetric) ? chosenMetric : metrics[0];
  const labels = [
    ...new Set(
      groups
        .filter((group) => group.metric === metric)
        .map((group) => group.label),
    ),
  ];
  const label = labels.includes(chosenLabel) ? chosenLabel : labels[0];
  const values =
    groups.find((group) => group.metric === metric && group.label === label)
      ?.values || {};
  const rows = Object.entries(values).sort(
    ([nameA, valueA], [nameB, valueB]) =>
      Math.abs(valueB) - Math.abs(valueA) || nameA.localeCompare(nameB),
  );
  const maxAbs = Math.max(...rows.map(([, value]) => Math.abs(value)), 0);

  return (
    <section className="viz-card wide analysis-score-card">
      <header>
        <div>
          <small>SCORES</small>
          <h3>{t("research.factor_scores")}</h3>
        </div>
        <div className="analysis-score-controls">
          <label>
            <span>{t("research.metric")}</span>
            <select
              value={metric}
              onChange={(event) => setChosenMetric(event.target.value)}
            >
              {metrics.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("research.label")}</span>
            <select
              value={label}
              onChange={(event) => setChosenLabel(event.target.value)}
            >
              {labels.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <span className="analysis-score-count">{rows.length}</span>
        </div>
      </header>
      <div className="analysis-score-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("research.factor")}</th>
              <th>{t("research.magnitude")}</th>
              <th>{t("research.score")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([factor, value]) => {
              const width = maxAbs ? (Math.abs(value) / maxAbs) * 50 : 0;
              return (
                <tr key={factor}>
                  <td>
                    <code>{factor}</code>
                  </td>
                  <td>
                    <div className="analysis-score-bar" aria-hidden="true">
                      <span
                        className={value < 0 ? "negative" : "positive"}
                        style={{
                          left: `${value < 0 ? 50 - width : 50}%`,
                          width: `${width}%`,
                        }}
                      />
                    </div>
                  </td>
                  <td>{fmt(value, 4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PredictionOverview({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const stats = meta.prediction_statistics;
  const columns = meta.output_columns?.length
    ? meta.output_columns
    : [
        "trade_date",
        "ts_code",
        "pred",
        "actual_return",
        "label_valid",
        "name",
        "is_buyable",
        ...(meta.index_weight_columns || []),
      ];
  const rate = (count?: number) =>
    count === undefined || !meta.rows
      ? "—"
      : `${fmt((count / meta.rows) * 100, 1)}%`;
  const indices = Object.entries(stats?.indices || {});
  return (
    <>
      <section className="viz-card wide prediction-overview-card">
        <header>
          <div>
            <small>OVERVIEW</small>
            <h3>{t("research.prediction_overview")}</h3>
          </div>
        </header>
        <div className="prediction-stat-grid">
          <div className="prediction-score-block">
            <small>{t("research.prediction_score_mean")}</small>
            <strong>{fmt(stats?.pred.mean, 4)}</strong>
            <div className="prediction-score-range">
              <span>
                {t("research.min")} <b>{fmt(stats?.pred.min, 4)}</b>
              </span>
              <span>
                {t("research.median")} <b>{fmt(stats?.pred.median, 4)}</b>
              </span>
              <span>
                {t("research.max")} <b>{fmt(stats?.pred.max, 4)}</b>
              </span>
            </div>
          </div>
          <div className="prediction-coverage-block">
            <small>{t("research.sample_coverage")}</small>
            <div>
              <span>{t("research.symbols_days")}</span>
              <strong>
                {fmt(stats?.symbols, 0)} / {fmt(stats?.days, 0)}
              </strong>
            </div>
            <div>
              <span>{t("research.buyable")}</span>
              <strong>{rate(stats?.buyable_rows)}</strong>
            </div>
            <div>
              <span>{t("research.valid_return")}</span>
              <strong>{rate(stats?.valid_return_rows)}</strong>
            </div>
            <div>
              <span>{t("research.backtest_candidates")}</span>
              <strong>{rate(stats?.candidate_rows)}</strong>
            </div>
          </div>
        </div>
        <div className="prediction-index-strip">
          <small>{t("research.index_weights")}</small>
          {indices.length ? (
            indices.map(([column, value]) => (
              <span key={column}>
                <code>{column.replace("index_weight_", "").toUpperCase()}</code>
                {fmt(value.constituents, 0)} {t("research.symbols")} ·{" "}
                {fmt(value.days_with_weights, 0)} {t("research.days")}
              </span>
            ))
          ) : (
            <span>
              {(meta.index_weight_columns || [])
                .map((column) =>
                  column.replace("index_weight_", "").toUpperCase(),
                )
                .join(" · ") || "—"}
            </span>
          )}
        </div>
      </section>
      <section className="viz-card wide prediction-columns-card">
        <header>
          <div>
            <small>SCHEMA</small>
            <h3>{t("research.result_columns")}</h3>
          </div>
          <span>{columns.length}</span>
        </header>
        <div className="prediction-column-grid">
          {columns.map((column) => (
            <div key={column}>
              <code>{column}</code>
              <span>
                {column.startsWith("index_weight_")
                  ? t("research.index_weight_decimal")
                  : t(`research.columns.${column}`, { defaultValue: "—" })}
              </span>
            </div>
          ))}
        </div>
        <p>{t("research.pred_is_a_ranking_score")}</p>
      </section>
    </>
  );
}

function BaseOutputView({ meta, kind }: { meta: Meta; kind: Kind }) {
  const { t } = useTranslation();
  const count =
    kind === "train"
      ? meta.train_rows
      : kind === "backtest"
        ? meta.days
        : meta.rows;
  const countLabel =
    kind === "train"
      ? t("research.train_rows")
      : kind === "backtest"
        ? t("research.days_2")
        : kind === "predict"
          ? t("research.prediction_rows")
          : t("research.rows");
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
                [
                  "daily_file",
                  meta.artifacts.daily?.path &&
                    `${meta._path}/${meta.artifacts.daily.path}`,
                ],
                [
                  "summary_file",
                  meta.artifacts.summary?.path &&
                    `${meta._path}/${meta.artifacts.summary.path}`,
                ],
              ];
  const columns =
    kind === "etl"
      ? [
          [t("research.feature_columns"), meta.feature_columns],
          [t("research.label_columns"), meta.label_columns],
        ]
      : kind === "train"
        ? [
            [t("research.feature_columns"), meta.feature_columns],
            [t("research.target_columns"), meta.target_columns],
          ]
        : [];
  const columnCards = columns.map(([title, values]) =>
    Array.isArray(values) && (values.length > 0 || kind === "train") ? (
      <section className="viz-card base-columns-card" key={String(title)}>
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
    ) : null,
  );
  return (
    <div className="artifact-content">
      <Kpis
        items={[
          { label: countLabel, value: fmt(count, 0) },
          ...(kind === "train"
            ? [
                {
                  label: t("research.model"),
                  value: meta.model_name || "—",
                },
              ]
            : []),
          ...(kind === "etl" || kind === "predict" || kind === "backtest"
            ? [
                {
                  label: t("research.start"),
                  value: meta.date_range?.start || "—",
                },
                {
                  label: t("research.end"),
                  value: meta.date_range?.end || "—",
                },
              ]
            : []),
          {
            label: t("research.artifacts"),
            value: fmt(Object.keys(meta.artifacts || {}).length, 0),
          },
        ]}
      />
      {kind === "train" ? (
        <div className="train-config-grid">
          {columnCards}
          <section className="viz-card train-parameters-card">
            <header>
              <div>
                <small>PARAMETERS</small>
                <h3>{t("research.effective_parameters")}</h3>
              </div>
              <span>{Object.keys(meta.parameters || {}).length}</span>
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
        </div>
      ) : kind === "predict" ? (
        <PredictionOverview meta={meta} />
      ) : (
        columnCards
      )}
      {kind === "analysis" && <AnalysisScores scores={meta.scores || {}} />}
      {kind === "train" && (
        <section className="viz-card wide train-curve-card">
          <header>
            <div>
              <small>TRAINING</small>
              <h3>{t("research.training_curves")}</h3>
            </div>
          </header>
          {meta.training_curve?.x.length ? (
            <Suspense
              fallback={
                <div className="research-loading">
                  <LoaderCircle className="spin" />
                </div>
              }
            >
              <TrainingCurveChart curve={meta.training_curve} />
            </Suspense>
          ) : (
            <div className="train-curve-empty">
              {t("research.no_training_curve_is_available")}
            </div>
          )}
          {meta.training_curve &&
            Object.keys(meta.training_curve.y_left).some((name) =>
              name.endsWith("_l2"),
            ) &&
            Object.keys(meta.training_curve.y_right).some((name) =>
              name.endsWith("_l1"),
            ) && (
              <p className="train-curve-note">
                {t("research.left_axis_l2_mean_squared")}
              </p>
            )}
          {Object.keys(meta.metrics || {}).length > 0 && (
            <div className="train-curve-metrics">
              {Object.entries(meta.metrics || {}).map(([name, value]) => (
                <span key={name}>
                  <small>{name}</small>
                  <strong>{fmt(value, 4)}</strong>
                </span>
              ))}
            </div>
          )}
        </section>
      )}
      <section className="viz-card base-files-card">
        <header>
          <div>
            <small>OUTPUT</small>
            <h3>{t("research.output_files")}</h3>
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
          <div className="artifact-input-dir">
            <small>{t("research.input_directory")}</small>
            <code>{meta.config.input_dir}</code>
          </div>
        )}
      </section>
      <section className="viz-card base-files-card">
        <header>
          <div>
            <small>ARTIFACTS</small>
            <h3>{t("research.artifacts_2")}</h3>
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
            <em>{formatBytes(file.size, false)}</em>
          </div>
        ))}
    </div>
  );
}
