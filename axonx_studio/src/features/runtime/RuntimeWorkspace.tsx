import { useEffect } from "react";
import {
  Activity,
  Cpu,
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
import { RailResizer } from "../../shared/ui/RailResizer";
import type { ContextOption, Language, MachineNode } from "../../types";

export function RuntimeWorkspace({
  language,
  machine,
  remoteIp,
  view,
  taskId,
  onNavigate,
  onSubmit,
  onOptionsChange,
  onConnection,
}: {
  language: Language;
  machine: MachineNode;
  remoteIp?: string;
  view: "resources" | "tasks" | "environment";
  taskId?: string;
  onNavigate: (
    view: "resources" | "tasks" | "environment",
    resource?: string,
  ) => void;
  onSubmit: () => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
  useEffect(() => {
    if (view !== "tasks" || !taskId || !onOptionsChange) return;
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
      <aside className="context-rail">
        <header>
          <small>RUNTIME</small>
          <strong>{zh ? "运行管理" : "Run management"}</strong>
        </header>
        <nav>
          <button
            className={view === "resources" ? "active" : ""}
            onClick={() => onNavigate("resources")}
          >
            <Cpu />
            <span>
              <strong>{zh ? "机器资源" : "Machine resources"}</strong>
              <small>
                {zh ? "当前机器的实时资源" : "Live resources for this machine"}
              </small>
            </span>
          </button>
          <button
            className={view === "tasks" ? "active" : ""}
            onClick={() => onNavigate("tasks")}
          >
            <Activity />
            <span>
              <strong>{zh ? "Task 管理" : "Task management"}</strong>
              <small>
                {zh ? "运行实例、日志与状态" : "Runs, logs and status"}
              </small>
            </span>
          </button>
          <button
            className={view === "environment" ? "active" : ""}
            onClick={() => onNavigate("environment")}
          >
            <SlidersHorizontal />
            <span>
              <strong>{zh ? "运行环境" : "Environment"}</strong>
              <small>
                {zh ? "版本与代码信息" : "Version and source details"}
              </small>
            </span>
          </button>
        </nav>
      </aside>
      <RailResizer min={240} max={440} className="context-resizer" />
      <main className="workspace-canvas">
        {view === "resources" ? (
          <CurrentMachineResources
            language={language}
            machine={machine}
            remoteIp={remoteIp}
            onConnection={onConnection}
          />
        ) : view === "environment" ? (
          <RuntimeEnvironment
            language={language}
            machine={machine}
            remoteIp={remoteIp}
            onConnection={onConnection}
          />
        ) : taskId ? (
          <TaskDetailPage
            taskId={taskId}
            language={language}
            remoteIp={remoteIp}
            onBack={() => onNavigate("tasks")}
            onConnection={onConnection}
          />
        ) : (
          <TasksPage
            language={language}
            remoteIp={remoteIp}
            onSubmit={onSubmit}
            onOpenTask={(id) => onNavigate("tasks", id)}
            onTasksChange={onOptionsChange}
            onConnection={onConnection}
          />
        )}
      </main>
    </section>
  );
}

function RuntimeEnvironment({
  language,
  machine,
  remoteIp,
  onConnection,
}: {
  language: Language;
  machine: MachineNode;
  remoteIp?: string;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
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
          <h1>{zh ? "运行环境" : "Environment"}</h1>
          <p>
            {zh
              ? "当前机器的 AxonX 与代码版本信息"
              : "AxonX and source revision for the current machine"}
          </p>
        </div>
        <button className="secondary-button" onClick={() => void reload()}>
          <RefreshCw className={loading ? "spin" : ""} />
          {zh ? "刷新" : "Refresh"}
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
          <h2>{zh ? "无法读取运行环境" : "Environment unavailable"}</h2>
          <p>{error}</p>
        </div>
      ) : (
        info && (
          <section className="runtime-environment-card">
            <header>
              <SlidersHorizontal />
              <strong>{zh ? "版本信息" : "Version information"}</strong>
            </header>
            <div>
              <EnvironmentValue
                label={zh ? "AxonX 版本" : "AXONX VERSION"}
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
                label={zh ? "服务地址" : "ENDPOINT"}
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
  language,
  machine,
  remoteIp,
  onConnection,
}: {
  language: Language;
  machine: MachineNode;
  remoteIp?: string;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
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
          <h1>{zh ? "机器资源" : "Machine resources"}</h1>
          <p className="machine-heading-meta">
            <span>
              <Server />
              {machine.address}
            </span>
            <span className="online">
              <i />
              {zh ? "在线" : "Online"}
            </span>
          </p>
        </div>
        <button className="secondary-button" onClick={() => void reload()}>
          <RefreshCw className={loading ? "spin" : ""} />
          {zh ? "刷新" : "Refresh"}
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
          <h2>{zh ? "无法连接当前机器" : "Machine unavailable"}</h2>
          <p>{error}</p>
        </div>
      ) : (
        info && <MachineDashboard node={node} language={language} />
      )}
    </section>
  );
}
