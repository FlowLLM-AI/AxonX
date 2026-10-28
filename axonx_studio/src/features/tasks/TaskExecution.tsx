import {
  ArrowUpRight,
  Braces,
  Cpu,
  LoaderCircle,
  Play,
  RotateCcw,
  SlidersHorizontal,
  Square,
  Terminal,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../../shared/lib/errors";
import {
  formSchema,
  initialSchemaValues,
  parseSchemaValues,
} from "../../shared/schema/values";
import { SchemaForm, SchemaOutput } from "../../shared/ui/SchemaForm";
import {
  executionActive,
  taskExecutions,
  useTaskExecutions,
  type TaskExecution,
  type TaskExecutionStore,
} from "./execution";
import type { TaskDefinition } from "./model";

const terminalColors = new RegExp(
  `${String.fromCharCode(27)}\\[[0-?]*[ -/]*[@-~]`,
  "g",
);
const readableLog = (text: string) => text.replace(terminalColors, "");

export function TaskRunForm({
  definition,
  target,
  machineId = "local",
  onOpenTask,
  store = taskExecutions,
}: {
  definition: TaskDefinition;
  target?: string;
  machineId?: string;
  onOpenTask?: (taskId: string) => void;
  store?: TaskExecutionStore;
}) {
  const { t } = useTranslation();
  const schema = useMemo(() => {
    const schema = formSchema(definition.input_schema);
    const properties = { ...schema.properties };
    if (properties.task_name)
      properties.task_name = {
        ...properties.task_name,
        title: t("taskExecution.taskName"),
        description: t("taskExecution.nameHint"),
      };
    if (properties.upstream_task_ids)
      properties.upstream_task_ids = {
        ...properties.upstream_task_ids,
        title: t("taskExecution.upstreamTasks"),
        description: t("taskExecution.upstreamHint"),
      };
    return { ...schema, properties };
  }, [definition, t]);
  const [values, setValues] = useState(() => initialSchemaValues(schema));
  const [error, setError] = useState("");
  const [pendingId, setPendingId] = useState<string>();
  const runs = useTaskExecutions(store);
  const run = runs.find((run) => run.id === pendingId);
  const busy = Boolean(run && executionActive(run));
  useEffect(() => {
    if (run?.task && onOpenTask) {
      setPendingId(undefined);
      onOpenTask(run.taskId);
    }
  }, [run?.task, run?.taskId, onOpenTask]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const parsed = parseSchemaValues(schema, values, {
      required: t("required"),
      invalidJson: t("taskExecution.invalidValue"),
    });
    if (Object.keys(parsed.errors).length) {
      setError(
        Object.entries(parsed.errors)
          .map(([name, message]) => `${name}: ${message}`)
          .join(" · "),
      );
      return;
    }
    try {
      setError("");
      setPendingId(
        store.start(definition, parsed.data, { target, machineId }).id,
      );
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };
  return (
    <>
      <form className="task-run-form" onSubmit={submit}>
        <div className="task-run-layout">
          <section className="configuration-card task-input-card">
            <header className="task-schema-heading">
              <SlidersHorizontal aria-hidden="true" />
              <div>
                <h3>{t("taskExecution.parameters")}</h3>
                <p>{t("taskExecution.parametersHint")}</p>
              </div>
            </header>
            <fieldset className="schema-fields" disabled={busy}>
              <SchemaForm
                schema={schema}
                values={values}
                onChange={setValues}
              />
            </fieldset>
          </section>
          <section className="configuration-card task-output-card">
            <header className="task-schema-heading">
              <Braces aria-hidden="true" />
              <div>
                <h3>{t("output")}</h3>
                <p>{t("taskExecution.outputHint")}</p>
              </div>
            </header>
            <SchemaOutput schema={definition.output_schema} />
          </section>
        </div>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <footer className="task-run-footer">
          <div className="task-run-target">
            <Cpu aria-hidden="true" />
            <div>
              <small>{t("taskExecution.target")}</small>
              <strong>{target || t("shell.local")}</strong>
            </div>
          </div>
          <p className="task-run-hint">{t("taskExecution.connectionHint")}</p>
          <div className="task-run-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => {
                setValues(initialSchemaValues(schema));
                setError("");
              }}
            >
              <RotateCcw />
              {t("taskExecution.reset")}
            </button>
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? <LoaderCircle className="spin" /> : <Play />}
              {t(busy ? "taskExecution.starting" : "taskExecution.run")}
            </button>
          </div>
        </footer>
      </form>
      {run && <TaskExecutionOutput run={run} store={store} />}
    </>
  );
}

export function TaskExecutionOutput({
  run,
  store = taskExecutions,
}: {
  run: TaskExecution;
  store?: TaskExecutionStore;
}) {
  const { t } = useTranslation();
  const viewport = useRef<HTMLPreElement>(null);
  const follow = useRef(true);
  useEffect(() => {
    if (viewport.current && follow.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [run.log]);
  return (
    <section
      className="task-execution-output"
      aria-label={t("taskExecution.output")}
    >
      <header>
        <Terminal />
        <strong>{t("taskExecution.output")}</strong>
        <span>
          {t(`taskExecution.states.${run.state}`)}
          {run.exitCode !== undefined &&
            ` · ${t("taskExecution.exitCode")} ${run.exitCode}`}
        </span>
        {executionActive(run) && run.task && (
          <button
            className="secondary-button"
            disabled={run.stopping}
            onClick={() => void store.stop(run.id)}
          >
            {run.stopping ? <LoaderCircle className="spin" /> : <Square />}
            {t("taskExecution.stop")}
          </button>
        )}
      </header>
      {run.error && (
        <p className="inline-error" role="alert">
          {readableLog(run.error)}
        </p>
      )}
      {run.state === "disconnected" && (
        <p className="task-run-hint">{t("taskExecution.disconnectedHint")}</p>
      )}
      <pre
        ref={viewport}
        tabIndex={0}
        onScroll={(event) => {
          const el = event.currentTarget;
          follow.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 30;
        }}
      >
        {readableLog(run.log) || t("taskExecution.waitingLog")}
      </pre>
    </section>
  );
}

export function TaskExecutionMonitor({
  onOpenTask,
}: {
  onOpenTask: (run: TaskExecution) => void;
}) {
  const { t } = useTranslation();
  const runs = useTaskExecutions();
  if (!runs.length) return null;
  const active = runs.filter(executionActive).length;
  return (
    <details className="task-execution-monitor">
      <summary>
        <Terminal />
        {t("taskExecution.monitor")}
        <span>
          {active
            ? t("taskExecution.active", { count: active })
            : t("taskExecution.finished")}
        </span>
      </summary>
      <div>
        {runs.map((run) => (
          <article key={run.id}>
            <div>
              <strong>{run.definition}</strong>
              <small>
                {run.target || t("shell.local")} ·{" "}
                {t(`taskExecution.states.${run.state}`)}
              </small>
            </div>
            {run.task && (
              <button
                aria-label={t("taskExecution.openTask")}
                title={t("taskExecution.openTask")}
                onClick={() => onOpenTask(run)}
              >
                <ArrowUpRight />
              </button>
            )}
            {!executionActive(run) && (
              <button
                aria-label={t("taskExecution.dismiss")}
                onClick={() => taskExecutions.dismiss(run.id)}
              >
                <X />
              </button>
            )}
            {run.error && <p>{readableLog(run.error)}</p>}
            {!run.task && (
              <details>
                <summary>{t("taskExecution.output")}</summary>
                <pre>
                  {readableLog(run.log || run.error) ||
                    t("taskExecution.waitingLog")}
                </pre>
              </details>
            )}
          </article>
        ))}
      </div>
    </details>
  );
}
