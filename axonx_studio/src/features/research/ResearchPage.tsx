import { Select } from "../../shared/ui/Select";
import { taskDirectory } from "../../shared/lib/tasks";
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
  GitCompareArrows,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { useCopyFeedback } from "../../shared/hooks/useCopyFeedback";
import { formatBytes } from "../../shared/lib/format";
import { parseSourceTasks } from "../../shared/lib/sourceTasks";
import { ReplicaNotice } from "../../shared/ReplicaNotice";
import { RailResizer } from "../../shared/ui/RailResizer";
import { RunIndexControls } from "../../shared/ui/RunIndexControls";
import { deleteWorkspaceEntries } from "../workspace/api";
import {
  countTrainingMembers,
  getResearchTask,
  listResearchTasks,
} from "./api";
import { fmt } from "./format";
import { PredictionOverview } from "./PredictionOverview";
import type { ResearchArtifact, ResearchKind, ResearchPageId } from "./types";

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
type TaskSummary = import("../tasks/types").TaskSummary;
type Kind = ResearchKind;

function useTasks(
  kind: Kind,
  target?: string,
  onConnection?: (online: boolean) => void,
) {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestId = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const load = useCallback(() => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    setTasks([]);
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    listResearchTasks(kind, target, controller.signal)
      .then((tasks) => {
        if (currentRequest !== requestId.current) return;
        setTasks(tasks);
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
  }, [kind, onConnection, target]);
  useEffect(() => {
    load();
    return () => {
      requestId.current += 1;
      requestController.current?.abort();
    };
  }, [load]);
  return { tasks, loading, error, load };
}

export default function ResearchPage({
  kind,
  target,
  initialSelectedId,
  onSelected,
  onOptionsChange,
  onConnection,
  onNavigate,
}: {
  kind: Kind;
  target?: string;
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
  const { tasks, loading, error, load } = useTasks(kind, target, onConnection);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [selectionMode, setSelectionMode] = useState(false);
  const [checked, setChecked] = useState<Record<string, TaskSummary>>({});
  const [deleteTargets, setDeleteTargets] = useState<TaskSummary[]>([]);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [contextMenu, setContextMenu] = useState<{
    task: TaskSummary;
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
        detail: task.reg_name || kind,
      })),
    );
  }, [tasks, kind, onOptionsChange]);
  useEffect(() => {
    setSelectionMode(false);
    setChecked({});
    setDeleteTargets([]);
    setContextMenu(null);
  }, [kind, target]);
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
    `${task.task_id} ${task.reg_name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const selectedCount = Object.keys(checked).length;
  const allVisibleSelected =
    visible.length > 0 &&
    visible.every((task) => checked[taskDirectory(task.task_id)]);
  const toggleTask = (task: TaskSummary) =>
    setChecked((current) => {
      const next = { ...current };
      if (next[taskDirectory(task.task_id)])
        delete next[taskDirectory(task.task_id)];
      else next[taskDirectory(task.task_id)] = task;
      return next;
    });
  const toggleVisible = () =>
    setChecked((current) => {
      const next = { ...current };
      for (const task of visible) {
        if (allVisibleSelected) delete next[taskDirectory(task.task_id)];
        else next[taskDirectory(task.task_id)] = task;
      }
      return next;
    });
  const confirmDelete = async () => {
    if (!deleteTargets.length) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteWorkspaceEntries(
        deleteTargets.map((task) => taskDirectory(task.task_id)),
        target,
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
            <RunIndexControls
              title={t("research.task_versions")}
              count={tasks.length}
              loading={loading}
              query={query}
              onQuery={setQuery}
              searchLabel={t("research.search_task_id")}
              refreshLabel={t("research.refresh")}
              onRefresh={load}
            />
            <div className="rail-scroll">
              {loading && !tasks.length ? (
                <span className="run-loading">
                  <LoaderCircle className="spin" />
                </span>
              ) : (
                visible.map((task) => (
                  <article
                    className={`${selectedId === task.task_id ? "active" : ""} ${checked[taskDirectory(task.task_id)] ? "checked" : ""}`}
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
                        aria-label={`${t("research.select")} ${task.task_id}`}
                        onClick={() => toggleTask(task)}
                      >
                        {checked[taskDirectory(task.task_id)] && <Check />}
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
                        {String(task.reg_name || kind)
                          .trim()
                          .slice(0, 1)
                          .toUpperCase()}
                      </span>
                      <span className="rail-item-copy">
                        <strong>{task.reg_name || kind}</strong>
                        <code>{task.task_id}</code>
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
              <SelectedArtifact
                key={`${target}:${selected.task_id}:${selected.run_id}`}
                kind={kind}
                taskId={selected.task_id}
                target={target}
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
            <span>{contextMenu.task.task_id}</span>
            <small>{contextMenu.task.reg_name || kind}</small>
          </header>
          <button
            role="menuitem"
            onClick={() => {
              setSelectionMode(true);
              if (!checked[taskDirectory(contextMenu.task.task_id)])
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
                <code key={taskDirectory(task.task_id)}>{task.task_id}</code>
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

function SelectedArtifact({
  kind,
  taskId,
  target,
  onNavigate,
}: {
  kind: Kind;
  taskId: string;
  target?: string;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const { t } = useTranslation();
  const load = useCallback(
    (signal: AbortSignal) => getResearchTask(kind, taskId, target, signal),
    [kind, taskId, target],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  if (error)
    return (
      <div className="error-banner" role="alert">
        {error}
        <button onClick={() => void reload()}>{t("research.retry")}</button>
      </div>
    );
  if (loading || !data)
    return (
      <div className="research-loading">
        <LoaderCircle className="spin" />
      </div>
    );
  return <ArtifactDetail meta={data} target={target} onNavigate={onNavigate} />;
}

function ArtifactDetail({
  meta,
  target,
  onNavigate,
}: {
  meta: Meta;
  target?: string;
  onNavigate: (page: ResearchPageId | "runtime", resource?: string) => void;
}) {
  const kind = meta.task_type;
  const { t } = useTranslation();
  const lineageClipboard = useCopyFeedback();
  const copiedLineage = lineageClipboard.copied;
  const pageByType: Partial<Record<string, ResearchPageId>> = {
    etl: "etl",
    analysis: "factors",
    train: "train",
    predict: "predict",
    backtest: "backtest",
  };
  const upstreams = parseSourceTasks(meta.input_params.source_tasks).map(
    (taskId) => ({
      taskId,
      type: taskId.split("#")[0],
      page: pageByType[taskId.split("#")[0]] || ("runtime" as const),
    }),
  );
  const copyLineageId = (taskId: string) => lineageClipboard.copy(taskId);
  return (
    <>
      {
        <header className="artifact-header">
          <div>
            <span className={`artifact-kind ${kind}`}>{iconFor(kind)}</span>
            <div className="artifact-title">
              <small>{meta.reg_name || kind}</small>
              <div className="artifact-title-row">
                <h2 title={meta.task_id}>{meta.task_id}</h2>
                <button
                  type="button"
                  className="artifact-id-copy"
                  onClick={() => void copyLineageId(meta.task_id)}
                  title={t("research.copy_task_id")}
                  aria-label={t("research.copy_task_id")}
                >
                  {copiedLineage === meta.task_id ? <Check /> : <Copy />}
                </button>
              </div>
            </div>
          </div>
          <div className="artifact-header-actions">
            {kind === "backtest" && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => onNavigate("compare", meta.task_id)}
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
      <ReplicaNotice replica={meta.replica} />
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
      {meta.task_type === "backtest" ? (
        <Suspense
          fallback={
            <div className="research-loading">
              <LoaderCircle className="spin" />
            </div>
          }
        >
          <BacktestView meta={meta} target={target} />
        </Suspense>
      ) : (
        <BaseOutputView meta={meta} target={target} />
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
            <Select
              value={metric}
              onChange={(event) => setChosenMetric(event.target.value)}
            >
              {metrics.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </label>
          <label>
            <span>{t("research.label")}</span>
            <Select
              value={label}
              onChange={(event) => setChosenLabel(event.target.value)}
            >
              {labels.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
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

function TrainingMemberCount({
  meta,
  target,
}: {
  meta: ResearchArtifact<"train">;
  target?: string;
}) {
  const load = useCallback(
    (signal: AbortSignal) => countTrainingMembers(meta, target, signal),
    [meta, target],
  );
  const { data, error } = useAsyncResource(load);
  return (
    <span title={error || undefined}>{data == null ? "—" : fmt(data, 0)}</span>
  );
}

function BaseOutputView({
  meta,
  target,
}: {
  meta: Exclude<Meta, { task_type: "backtest" }>;
  target?: string;
}) {
  const kind = meta.task_type;
  const { t } = useTranslation();
  const train = meta.task_type === "train" ? meta.output_params : null;
  const etl = meta.task_type === "etl" ? meta.output_params : null;
  const predict = meta.task_type === "predict" ? meta.output_params : null;
  const analysis = meta.task_type === "analysis" ? meta.output_params : null;
  const count =
    train?.train_rows ??
    ("rows" in meta.output_params ? meta.output_params.rows : undefined);
  const countLabel =
    kind === "train"
      ? t("research.train_rows")
      : kind === "predict"
        ? t("research.prediction_rows")
        : t("research.rows");
  const paths = Object.entries(meta.output_params.artifacts).map(
    ([name, artifact]) => [
      name,
      `${taskDirectory(meta.task_id)}/${artifact.path}`,
    ],
  );
  const members = Object.entries(
    (("protocol" in meta.output_params
      ? meta.output_params.protocol.score_columns
      : undefined) || {}) as Record<string, string>,
  );
  const columns =
    kind === "etl"
      ? [
          [
            t("research.feature_columns"),
            etl?.feature_columns ?? train?.feature_columns,
          ],
          [t("research.label_columns"), etl?.label_columns],
        ]
      : kind === "train"
        ? [
            [
              t("research.feature_columns"),
              etl?.feature_columns ?? train?.feature_columns,
            ],
            [t("research.target_columns"), train?.target_columns],
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
                  value: train?.model_name || "—",
                },
              ]
            : []),
          ...(kind === "train" || kind === "predict"
            ? [
                {
                  label: t("research.model_members"),
                  value:
                    meta.task_type === "train" ? (
                      <TrainingMemberCount meta={meta} target={target} />
                    ) : (
                      fmt(members.length, 0)
                    ),
                },
              ]
            : []),
          ...(kind === "etl" || kind === "predict"
            ? [
                {
                  label: t("research.start"),
                  value: (etl?.date_range ?? predict?.date_range)?.start || "—",
                },
                {
                  label: t("research.end"),
                  value: (etl?.date_range ?? predict?.date_range)?.end || "—",
                },
              ]
            : []),
          {
            label: t("research.artifacts"),
            value: fmt(
              Object.keys(meta.output_params.artifacts || {}).length,
              0,
            ),
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
              <span>{Object.keys(train?.parameters || {}).length}</span>
            </header>
            <div className="base-value-list">
              {Object.entries(train?.parameters || {}).map(([name, value]) => (
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
      ) : meta.task_type === "predict" ? (
        <PredictionOverview meta={meta} />
      ) : (
        columnCards
      )}
      {kind === "predict" && members.length > 0 && (
        <section className="viz-card wide">
          <header>
            <h3>{t("research.score_columns")}</h3>
            <span>{members.length}</span>
          </header>
          <div className="base-value-list">
            {members.map(([member, column]) => (
              <div key={member}>
                <code>{member}</code>
                <strong>{column}</strong>
              </div>
            ))}
          </div>
        </section>
      )}
      {kind === "analysis" && (
        <AnalysisScores scores={analysis?.scores || {}} />
      )}
      {kind === "train" && (
        <section className="viz-card wide train-curve-card">
          <header>
            <div>
              <small>TRAINING</small>
              <h3>{t("research.training_curves")}</h3>
            </div>
          </header>
          {train?.training_curve?.x.length ? (
            <Suspense
              fallback={
                <div className="research-loading">
                  <LoaderCircle className="spin" />
                </div>
              }
            >
              <TrainingCurveChart curve={train?.training_curve} />
            </Suspense>
          ) : (
            <div className="train-curve-empty">
              {t("research.no_training_curve_is_available")}
            </div>
          )}
          {train?.training_curve &&
            Object.keys(train?.training_curve.y_left).some((name) =>
              name.endsWith("_l2"),
            ) &&
            Object.keys(train?.training_curve.y_right).some((name) =>
              name.endsWith("_l1"),
            ) && (
              <p className="train-curve-note">
                {t("research.left_axis_l2_mean_squared")}
              </p>
            )}
          {Object.keys(train?.metrics || {}).length > 0 && (
            <div className="train-curve-metrics">
              {Object.entries(train?.metrics || {}).map(([name, value]) => (
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
        {kind === "etl" && typeof meta.input_params.input_dir === "string" && (
          <div className="artifact-input-dir">
            <small>{t("research.input_directory")}</small>
            <code>{String(meta.input_params.input_dir)}</code>
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
        <ArtifactRecords meta={meta} />
      </section>
    </div>
  );
}

function ArtifactRecords({ meta }: { meta: Meta }) {
  return (
    <div className="artifact-files">
      {Object.entries(meta.output_params.artifacts || {}).map(
        ([name, file]) => (
          <div key={name}>
            <FileSpreadsheet />
            <span>
              <strong>{name}</strong>
              <code>{file.path}</code>
            </span>
            <em>{formatBytes(file.size, false)}</em>
          </div>
        ),
      )}
    </div>
  );
}
