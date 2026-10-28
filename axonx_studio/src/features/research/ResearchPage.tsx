import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckSquare2,
  Database,
  LoaderCircle,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import { deleteWorkspaceEntries } from "../../shared/api/workspace";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { taskDirectory } from "../../shared/lib/tasks";
import { RailResizer } from "../../shared/ui/RailResizer";
import { TaskIndexControls } from "../../shared/ui/TaskIndexControls";
import { listResearchTasks } from "./api";
import { ResearchDetail } from "./ResearchDetail";
import type { ResearchKind, ResearchPageId } from "./types";

const EMPTY_TASKS: TaskSummary[] = [];

type TaskSummary = import("../../shared/api/contracts").TaskSummary;

export default function ResearchPage({
  kind,
  target,
  initialSelectedId,
  onSelected,
  onOptionsChange,
  onConnection,
  onNavigate,
}: {
  kind: ResearchKind;
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
  const request = useCallback(
    async (signal: AbortSignal) => {
      try {
        const result = await listResearchTasks(kind, { target, signal });
        signal.throwIfAborted();
        onConnection(true);
        return result;
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [kind, target, onConnection],
  );
  const { data, loading, error, reload: load } = useAsyncResource(request);
  const tasks = data ?? EMPTY_TASKS;
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
        { target },
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
            className={`task-index rail-panel ${selectionMode ? "selecting" : ""}`}
          >
            <TaskIndexControls
              title={t("research.task_list")}
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
                <span className="task-loading">
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
                        className="task-check"
                        aria-label={`${t("research.select")} ${task.task_id}`}
                        onClick={() => toggleTask(task)}
                      >
                        {checked[taskDirectory(task.task_id)] && <Check />}
                      </button>
                    )}
                    <button
                      className="task-main rail-list-item"
                      onClick={() =>
                        selectionMode
                          ? toggleTask(task)
                          : (setSelectedId(task.task_id),
                            onSelected?.(task.task_id))
                      }
                    >
                      <span
                        className={`task-item-avatar rail-avatar task-kind-${kind}`}
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
              <footer className="task-selection">
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
              <ResearchDetail
                key={`${target}:${selected.task_id}:${selected.started_at}`}
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
                      ? t("research.select_a_task")
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
                ? t("research.delete_selected_task_list")
                : t("research.delete_this_task")}
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
