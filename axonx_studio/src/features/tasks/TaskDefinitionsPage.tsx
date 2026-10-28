import {
  Braces,
  ChevronDown,
  ChevronRight,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { RailResizer } from "../../shared/ui/RailResizer";
import { listTaskDefs } from "./api";
import type { TaskDefinition } from "./model";
import { TaskRunForm } from "./TaskExecution";

const EMPTY_TASKS: TaskDefinition[] = [];

export default function TaskDefinitionsPage({
  target,
  initialName,
  onSelected,
  onOptionsChange,
  onConnection,
  machineId,
  onOpenTask,
}: {
  target?: string;
  initialName?: string;
  onSelected?: (name: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
  machineId?: string;
  onOpenTask?: (taskId: string) => void;
}) {
  const { t } = useTranslation();
  const [selectedName, setSelectedName] = useState("");
  const [search, setSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );

  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const result = await listTaskDefs({ target, signal });
        signal.throwIfAborted();
        onConnection(true);
        return result;
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [onConnection, target],
  );
  const { data, loading, error, reload } = useAsyncResource(load);
  const tasks = data || EMPTY_TASKS;

  useEffect(() => {
    if (initialName && tasks.some((task) => task.name === initialName))
      setSelectedName(initialName);
  }, [initialName, tasks]);
  useEffect(() => {
    onOptionsChange?.(
      tasks.map((task) => ({
        value: task.name,
        label: task.name,
        detail: t(`types.${task.task_type}`, task.task_type),
      })),
    );
  }, [tasks, t, onOptionsChange]);
  const selected = tasks.find((task) => task.name === selectedName);
  const filtered = useMemo(
    () =>
      tasks.filter((task) =>
        `${task.name} ${task.task_type} ${task.description}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      ),
    [tasks, search],
  );
  const taskGroups = useMemo(() => {
    const plugins = new Map<string, TaskDefinition[]>();
    for (const task of filtered) {
      if (task.source !== "plugin") continue;
      const plugin = task.plugin || t("pluginTasks");
      const group = plugins.get(plugin) || [];
      group.push(task);
      plugins.set(plugin, group);
    }
    return [
      {
        id: "native",
        label: t("nativeTasks"),
        tasks: filtered.filter((task) => task.source !== "plugin"),
      },
      ...Array.from(plugins, ([plugin, pluginTasks]) => ({
        id: `plugin:${plugin}`,
        label: plugin,
        tasks: pluginTasks,
      })).sort((a, b) => a.label.localeCompare(b.label)),
    ];
  }, [filtered, t]);

  const chooseTask = (name: string) => {
    setSelectedName(name);
    onSelected?.(name);
  };
  const toggleGroup = (id: string) =>
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <section className="workspace-page task-definitions-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TASK DEFINITIONS / 02</p>
          <h1>{t("taskDefinitionsTitle")}</h1>
          <span>{t("taskDefinitionsLead")}</span>
        </div>
      </div>
      <div className="task-definitions-layout">
        <aside className="catalog-panel rail-panel">
          <header className="catalog-header rail-header">
            <div className="catalog-heading rail-heading">
              <strong>{t("taskCatalog")}</strong>
              <span>{t("tasksAvailable", { count: tasks.length })}</span>
            </div>
            <button
              className="catalog-refresh rail-refresh"
              onClick={() => void reload()}
              aria-label={t("refresh")}
            >
              <RefreshCw className={loading ? "spin" : ""} />
            </button>
          </header>
          <label className="context-search rail-search">
            <Search />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("findTask")}
            />
          </label>
          <div className="task-catalog rail-scroll">
            {taskGroups.map((group) => {
              if (!group.tasks.length) return null;
              const expanded =
                (group.id === "native"
                  ? !collapsedGroups.has(group.id)
                  : collapsedGroups.has(group.id)) || Boolean(search.trim());
              const itemsId = `task-group-${group.id}`;
              return (
                <section
                  className={`task-catalog-group ${expanded ? "expanded" : "collapsed"}`}
                  key={group.id}
                >
                  <button
                    type="button"
                    className="catalog-group-toggle"
                    aria-expanded={expanded}
                    aria-controls={itemsId}
                    onClick={() => toggleGroup(group.id)}
                  >
                    <span>
                      <ChevronDown />
                      {group.label}
                    </span>
                    <small>{group.tasks.length}</small>
                  </button>
                  {expanded && (
                    <div className="task-catalog-items" id={itemsId}>
                      {group.tasks.map((task) => (
                        <CatalogTask
                          key={task.name}
                          task={task}
                          typeLabel={t(
                            `types.${task.task_type}`,
                            task.task_type,
                          )}
                          active={selectedName === task.name}
                          onChoose={chooseTask}
                        />
                      ))}
                    </div>
                  )}
                </section>
              );
            })}
            {!loading && !filtered.length && (
              <div className="catalog-empty">{t("noInstalled")}</div>
            )}
          </div>
        </aside>
        <RailResizer min={180} max={460} className="context-resizer" />
        <div className="form-panel">
          {loading && !selected && (
            <div className="loading-state tall">
              <LoaderCircle className="spin" />{" "}
              {t("taskDefinitions.loadingCatalog")}
            </div>
          )}
          {error && !selected && (
            <div className="form-message error">
              <Braces />
              <h2>{t("catalogFailed")}</h2>
              <p>{error}</p>
              <button
                className="secondary-button"
                onClick={() => void reload()}
              >
                {t("retry")}
              </button>
            </div>
          )}
          {!loading && !error && !selected && (
            <div className="empty-workspace">
              <Sparkles />
              <strong>{t("taskDefinitions.selectTask")}</strong>
              <span>{t("taskDefinitions.selectTaskHint")}</span>
            </div>
          )}
          {selected && (
            <article>
              <header className={`task-form-header type-${selected.task_type}`}>
                <div className="large-task-icon">
                  <Sparkles />
                </div>
                <div>
                  <span className="type-label">
                    {t(`types.${selected.task_type}`, selected.task_type)}
                  </span>
                  <h2>{selected.name}</h2>
                  <p>{selected.description}</p>
                </div>
              </header>
              <TaskRunForm
                key={`${target}:${selected.name}`}
                definition={selected}
                target={target}
                machineId={machineId}
                onOpenTask={onOpenTask}
              />
            </article>
          )}
        </div>
      </div>
    </section>
  );
}

function CatalogTask({
  task,
  typeLabel,
  active,
  onChoose,
}: {
  task: TaskDefinition;
  typeLabel: string;
  active: boolean;
  onChoose: (name: string) => void;
}) {
  return (
    <button
      type="button"
      className={`catalog-task rail-list-item${active ? " active" : ""}`}
      aria-pressed={active}
      onClick={() => onChoose(task.name)}
    >
      <span className={`catalog-icon rail-avatar type-${task.task_type}`}>
        {task.name.trim().slice(0, 1).toUpperCase()}
      </span>
      <span className="catalog-task-copy rail-item-copy">
        <strong title={task.name}>{task.name}</strong>
        <small>{typeLabel}</small>
      </span>
      <ChevronRight />
    </button>
  );
}
