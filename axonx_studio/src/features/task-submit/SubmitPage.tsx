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
import { interpolate, t } from "../../i18n";
import { RailResizer } from "../../shared/ui/RailResizer";
import {
  initialSchemaValues,
  parseSchemaValues,
} from "../../shared/schema/values";
import type { SchemaFormValues } from "../../shared/schema/values";
import { SchemaField } from "../../shared/ui/SchemaForm/SchemaField";
import type { ContextOption, Language, TaskDefinition } from "../../types";

export function SubmitPage({
  language,
  remoteIp,
  initialName,
  onSelected,
  onOptionsChange,
  onViewTasks,
  onConnection,
}: {
  language: Language;
  remoteIp?: string;
  initialName?: string;
  onSelected?: (name: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onViewTasks: () => void;
  onConnection: (online: boolean) => void;
}) {
  const text = t(language);
  const [tasks, setTasks] = useState<TaskDefinition[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState<SchemaFormValues>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<
    Set<TaskDefinition["source"]>
  >(new Set());

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
        detail: text.types[task.task_type] || task.task_type,
      })),
    );
  }, [tasks, text.types, onOptionsChange]);
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
  const taskGroups = useMemo(
    () => [
      {
        source: "native" as const,
        label: text.nativeTasks,
        tasks: filtered.filter((task) => task.source !== "plugin"),
      },
      {
        source: "plugin" as const,
        label: text.pluginTasks,
        tasks: filtered.filter((task) => task.source === "plugin"),
      },
    ],
    [filtered, text.nativeTasks, text.pluginTasks],
  );

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
  const toggleGroup = (source: TaskDefinition["source"]) =>
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const { data: parsed, errors } = parseSchemaValues(
      selected.input_schema,
      values,
      {
        required: text.required,
        invalidJson: text.jsonHint,
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
          <h1>{text.submitTitle}</h1>
          <span>{text.submitLead}</span>
        </div>
      </div>
      <div className="submit-layout">
        <aside className="catalog-panel rail-panel">
          <header className="catalog-header rail-header">
            <div className="catalog-heading rail-heading">
              <strong>{text.taskCatalog}</strong>
              <span>
                {interpolate(text.tasksAvailable, { count: tasks.length })}
              </span>
            </div>
            <button
              className="catalog-refresh rail-refresh"
              onClick={() => void load()}
              aria-label="Refresh"
            >
              <RefreshCw className={loading ? "spin" : ""} />
            </button>
          </header>
          <label className="context-search rail-search">
            <Search />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={text.findTask}
            />
          </label>
          <div className="task-catalog rail-scroll">
            {taskGroups.map((group) => {
              if (!group.tasks.length) return null;
              const expanded =
                !collapsedGroups.has(group.source) || Boolean(search.trim());
              const itemsId = `task-group-${group.source}`;
              return (
                <section
                  className={`task-catalog-group ${expanded ? "expanded" : "collapsed"}`}
                  key={group.source}
                >
                  <button
                    type="button"
                    className="catalog-group-toggle"
                    aria-expanded={expanded}
                    aria-controls={itemsId}
                    onClick={() => toggleGroup(group.source)}
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
                          typeLabel={
                            text.types[task.task_type] || task.task_type
                          }
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
              <div className="catalog-empty">{text.noInstalled}</div>
            )}
          </div>
        </aside>
        <RailResizer min={180} max={460} className="context-resizer" />
        <div className="form-panel">
          {loading && !selected && (
            <div className="loading-state tall">
              <LoaderCircle className="spin" /> Loading Task catalog…
            </div>
          )}
          {error && !selected && (
            <div className="form-message error">
              <Braces />
              <h2>{text.catalogFailed}</h2>
              <p>{error}</p>
              <button className="secondary-button" onClick={() => void load()}>
                {text.retry}
              </button>
            </div>
          )}
          {!loading && !error && !selected && (
            <div className="empty-workspace">
              <Sparkles />
              <strong>
                {language === "zh" ? "选择一个 Task" : "Select a Task"}
              </strong>
              <span>
                {language === "zh"
                  ? "查看说明、配置参数并提交运行"
                  : "Review its inputs and submit a run"}
              </span>
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
                    {text.types[selected.task_type] || selected.task_type}
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
                    <span>{text.configure}</span>
                  </div>
                  <small>
                    {
                      Object.keys(selected.input_schema.properties || {})
                        .length
                    }{" "}
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
                        language={language}
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
              {!!Object.keys(selected.output_schema.properties || {}).length && (
                <div className="output-preview">
                  <span>
                    <Braces />
                    {text.output}
                  </span>
                  <div>
                    {Object.keys(selected.output_schema.properties || {}).map((key) => (
                      <code key={key}>{key}</code>
                    ))}
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
                  {submitting ? text.submitting : text.submit}
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
              <h2>{text.submitted}</h2>
              <span>{text.submittedHint}</span>
              <code>{selected.name}</code>
              <button className="primary-button" onClick={onViewTasks}>
                {text.viewTasks}
                <ArrowRight />
              </button>
              <button
                className="link-button"
                onClick={() => setSubmitted(false)}
              >
                {language === "zh" ? "再提交一次" : "Submit another"}
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
