import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Braces,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  LoaderCircle,
  RefreshCw,
  Search,
  Send,
  Sparkles,
} from "lucide-react";
import { listInstalledTaskDefinitions, submitTask } from "../tasks/api";
import { useTranslation } from "react-i18next";
import { RailResizer } from "../../shared/ui/RailResizer";
import {
  initialSchemaValues,
  parseSchemaValues,
} from "../../shared/schema/values";
import type { SchemaFormValues } from "../../shared/schema/values";
import { SchemaField } from "../../shared/ui/SchemaForm/SchemaField";
import type { ContextOption } from "../../app/types";
import type { TaskDefinition } from "../tasks/types";

export function SubmitPage({
  remoteIp,
  initialName,
  onSelected,
  onOptionsChange,
  onViewTasks,
  onConnection,
}: {
  remoteIp?: string;
  initialName?: string;
  onSelected?: (name: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onViewTasks: () => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<TaskDefinition[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState<SchemaFormValues>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set(),
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listInstalledTaskDefinitions(remoteIp);
      setTasks(result);
      setSelectedName((current) =>
        result.some((task) => task.name === current) ? current : "",
      );
      onConnection(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
    } finally {
      setLoading(false);
    }
  }, [onConnection, remoteIp]);

  useEffect(() => {
    void load();
  }, [load]);
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

  useEffect(() => {
    if (!selected) return;
    setValues(initialSchemaValues(selected.input_schema));
    setFieldErrors({});
    setSubmitted(false);
  }, [selectedName, selected]);

  const chooseTask = (name: string) => {
    setSelectedName(name);
    setSubmitted(false);
    onSelected?.(name);
  };
  const toggleGroup = (id: string) =>
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const { data: parsed, errors } = parseSchemaValues(
      selected.input_schema,
      values,
      {
        required: t("required"),
        invalidJson: t("jsonHint"),
      },
    );
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
    setSubmitting(true);
    setError("");
    try {
      await submitTask(selected.name, parsed, remoteIp);
      setSubmitted(true);
      onConnection(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="workspace-page submit-workspace">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TASK LAUNCHER / 02</p>
          <h1>{t("submitTitle")}</h1>
          <span>{t("submitLead")}</span>
        </div>
      </div>
      <div className="submit-layout">
        <aside className="catalog-panel rail-panel">
          <header className="catalog-header rail-header">
            <div className="catalog-heading rail-heading">
              <strong>{t("taskCatalog")}</strong>
              <span>{t("tasksAvailable", { count: tasks.length })}</span>
            </div>
            <button
              className="catalog-refresh rail-refresh"
              onClick={() => void load()}
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
              <LoaderCircle className="spin" /> {t("submitPage.loadingCatalog")}
            </div>
          )}
          {error && !selected && (
            <div className="form-message error">
              <Braces />
              <h2>{t("catalogFailed")}</h2>
              <p>{error}</p>
              <button className="secondary-button" onClick={() => void load()}>
                {t("retry")}
              </button>
            </div>
          )}
          {!loading && !error && !selected && (
            <div className="empty-workspace">
              <Sparkles />
              <strong>{t("submitPage.selectTask")}</strong>
              <span>{t("submitPage.selectTaskHint")}</span>
            </div>
          )}
          {selected && !submitted && (
            <form onSubmit={(event) => void submit(event)}>
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
              <section className="configuration-card">
                <div className="form-section-heading">
                  <div>
                    <span className="section-heading-icon">
                      <CircleDot />
                    </span>
                    <span>{t("configure")}</span>
                  </div>
                  <small>
                    {Object.keys(selected.input_schema.properties || {}).length}{" "}
                    fields
                  </small>
                </div>
                <div className="dynamic-form">
                  {Object.entries(selected.input_schema.properties || {}).map(
                    ([name, schema]) => (
                      <SchemaField
                        key={name}
                        name={name}
                        schema={schema}
                        required={(
                          selected.input_schema.required || []
                        ).includes(name)}
                        value={values[name] ?? ""}
                        error={fieldErrors[name]}
                        onChange={(value) =>
                          setValues((current) => ({
                            ...current,
                            [name]: value,
                          }))
                        }
                      />
                    ),
                  )}
                </div>
              </section>
              {!!Object.keys(selected.output_schema.properties || {})
                .length && (
                <div className="output-preview">
                  <span>
                    <Braces />
                    {t("output")}
                  </span>
                  <div>
                    {Object.keys(selected.output_schema.properties || {}).map(
                      (key) => (
                        <code key={key}>{key}</code>
                      ),
                    )}
                  </div>
                </div>
              )}
              {error && <div className="inline-error">{error}</div>}
              <footer className="form-footer">
                <span>POST /jobs/submit</span>
                <button
                  className="primary-button submit-button"
                  disabled={submitting}
                >
                  {submitting ? <LoaderCircle className="spin" /> : <Send />}{" "}
                  {submitting ? t("submitting") : t("submit")}
                  <ArrowRight />
                </button>
              </footer>
            </form>
          )}
          {selected && submitted && (
            <div className="success-state">
              <span className="success-rings">
                <i />
                <i />
                <Check />
              </span>
              <p>SUBMITTED</p>
              <h2>{t("submitted")}</h2>
              <span>{t("submittedHint")}</span>
              <code>{selected.name}</code>
              <button className="primary-button" onClick={onViewTasks}>
                {t("viewTasks")}
                <ArrowRight />
              </button>
              <button
                className="link-button"
                onClick={() => setSubmitted(false)}
              >
                {t("submitPage.submitAnother")}
              </button>
            </div>
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
