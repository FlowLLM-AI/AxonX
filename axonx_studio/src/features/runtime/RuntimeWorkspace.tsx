import { useEffect } from "react";
import {
  GitBranch,
  GitCommitHorizontal,
  LoaderCircle,
  RefreshCw,
  Server,
  SlidersHorizontal,
} from "lucide-react";
import { MachineDashboard } from "../machines/MachineDashboard";
import { useMachineInfo } from "../machines/useMachineInfo";
import { listTaskStatuses } from "../tasks/api";
import { TaskDetailPage } from "../tasks/TaskDetailPage";
import { TasksPage } from "../tasks/TasksPage";
import type { ContextOption } from "../../app/types";
import type { MachineNode } from "../machines/types";
import { useTranslation } from "react-i18next";

export function RuntimeWorkspace({
  machine,
  remoteIp,
  view,
  taskId,
  onNavigate,
  onSubmit,
  onOptionsChange,
  onConnection,
}: {
  machine: MachineNode;
  remoteIp?: string;
  view:
    "resources" | "tasks" | "environment" | "overview" | "logs" | "relations";
  taskId?: string;
  onNavigate: (
    view:
      "resources" | "tasks" | "environment" | "overview" | "logs" | "relations",
    resource?: string,
  ) => void;
  onSubmit: () => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  useEffect(() => {
    if (
      !["overview", "logs", "relations"].includes(view) ||
      !taskId ||
      !onOptionsChange
    )
      return;
    const controller = new AbortController();
    listTaskStatuses(remoteIp, controller.signal)
      .then((tasks) =>
        onOptionsChange(
          tasks.map((task) => ({
            value: task.task_id,
            label: task.task_id,
            detail: task.task_name || task.task_type,
          })),
        ),
      )
      .catch(() => undefined);
    return () => controller.abort();
  }, [view, taskId, remoteIp, onOptionsChange]);
  return (
    <section className="runtime-workspace unified-workspace">
      <main className="workspace-canvas">
        {view === "resources" ? (
          <CurrentMachineResources
            machine={machine}
            remoteIp={remoteIp}
            onConnection={onConnection}
          />
        ) : view === "environment" ? (
          <RuntimeEnvironment
            machine={machine}
            remoteIp={remoteIp}
            onConnection={onConnection}
          />
        ) : view !== "tasks" && taskId ? (
          <TaskDetailPage
            taskId={taskId}
            tab={view as "overview" | "logs" | "relations"}
            remoteIp={remoteIp}
            onBack={() => onNavigate("tasks")}
            onTabChange={(tab) => onNavigate(tab, taskId)}
            onOpenTask={(id) => onNavigate("overview", id)}
            onConnection={onConnection}
          />
        ) : (
          <TasksPage
            remoteIp={remoteIp}
            onSubmit={onSubmit}
            onOpenTask={(id) => onNavigate("overview", id)}
            onOpenGraph={(id) => onNavigate("relations", id)}
            onTasksChange={onOptionsChange}
            onConnection={onConnection}
          />
        )}
      </main>
    </section>
  );
}

function RuntimeEnvironment({
  machine,
  remoteIp,
  onConnection,
}: {
  machine: MachineNode;
  remoteIp?: string;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const {
    data: info,
    loading,
    error,
    reload,
  } = useMachineInfo(remoteIp, onConnection);
  return (
    <section className="runtime-environment-page">
      <header className="canvas-heading">
        <div>
          <small>RUNTIME / ENVIRONMENT</small>
          <h1>{t("runtime.environment")}</h1>
          <p>{t("runtime.environmentLead")}</p>
        </div>
        <button className="secondary-button" onClick={() => void reload()}>
          <RefreshCw className={loading ? "spin" : ""} />
          {t("refresh")}
        </button>
      </header>
      {loading && !info ? (
        <div className="loading-state machine-loading">
          <LoaderCircle className="spin" />
        </div>
      ) : error ? (
        <div className="machine-offline">
          <span>
            <Server />
          </span>
          <h2>{t("runtime.environmentUnavailable")}</h2>
          <p>{error}</p>
        </div>
      ) : (
        info && (
          <section className="runtime-environment-card">
            <header>
              <SlidersHorizontal />
              <strong>{t("runtime.versionInformation")}</strong>
            </header>
            <div>
              <EnvironmentValue
                label={t("runtime.axonxVersion")}
                value={`v${info.axonx.version}`}
              />
              <EnvironmentValue
                label="GIT COMMIT"
                value={info.axonx.git_commit || "—"}
                icon={<GitCommitHorizontal />}
              />
              <EnvironmentValue
                label="GIT BRANCH"
                value={info.axonx.git_branch || "—"}
                icon={<GitBranch />}
              />
              <EnvironmentValue
                label={t("runtime.endpoint")}
                value={machine.address}
              />
            </div>
          </section>
        )
      )}
    </section>
  );
}

function EnvironmentValue({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
}) {
  return (
    <article>
      <small>{label}</small>
      <strong>
        {icon}
        {value}
      </strong>
    </article>
  );
}

function CurrentMachineResources({
  machine,
  remoteIp,
  onConnection,
}: {
  machine: MachineNode;
  remoteIp?: string;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const {
    data: info,
    loading,
    error,
    reload,
  } = useMachineInfo(remoteIp, onConnection);
  const node = info ? { ...machine, info } : machine;
  return (
    <section className="current-machine-page">
      <header className="canvas-heading">
        <div>
          <small>MACHINE / LIVE</small>
          <h1>{t("runtime.machineResources")}</h1>
          <p className="machine-heading-meta">
            <span>
              <Server />
              {machine.address}
            </span>
            <span className="online">
              <i />
              {t("shell.online")}
            </span>
          </p>
        </div>
        <button
          className="secondary-button machine-refresh-button"
          onClick={() => void reload()}
          aria-label={t("runtime.refreshMachine")}
          title={t("runtime.refreshMachine")}
        >
          <RefreshCw className={loading ? "spin" : ""} />
        </button>
      </header>
      {loading && !info ? (
        <div className="loading-state machine-loading">
          <LoaderCircle className="spin" />
        </div>
      ) : error ? (
        <div className="machine-offline">
          <span>
            <Server />
          </span>
          <h2>{t("runtime.machineUnavailable")}</h2>
          <p>{error}</p>
        </div>
      ) : (
        info && <MachineDashboard node={node} />
      )}
    </section>
  );
}
