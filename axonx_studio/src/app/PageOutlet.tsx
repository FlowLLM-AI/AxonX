import { lazy, Suspense, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import { operationPages } from "../features/operations/pages";
import type { ResearchPageId } from "../features/research/types";
import type { MachineNode } from "../features/runtime/machine";
import { researchSections } from "./navigation";
import type { AppRoute, SectionId } from "./routes";
import { defaultRoute } from "./routes";
import type { ContextOption } from "./types";

const OperationPage = lazy(
  () => import("../features/operations/OperationPage"),
);
const ReportPage = lazy(() => import("../features/operations/ReportPage"));
const HomePage = lazy(() => import("../features/HomePage"));
const RuntimeWorkspace = lazy(
  () => import("../features/runtime/RuntimeWorkspace"),
);
const WorkspaceBrowserPage = lazy(
  () => import("../features/workspace/WorkspaceBrowserPage"),
);
const ResearchPage = lazy(() => import("../features/research/ResearchPage"));
const StrategyComparePage = lazy(
  () => import("../features/research/compare/StrategyComparePage"),
);
const ApiWorkspace = lazy(() => import("../features/api-catalog/ApiWorkspace"));
const TaskDefinitionsPage = lazy(
  () => import("../features/tasks/TaskDefinitionsPage"),
);
const AgentWorkspace = lazy(() => import("../features/agent/AgentWorkspace"));

interface PageOutletProps {
  route: AppRoute;
  machine: MachineNode;
  target?: string;
  navigate: (route: AppRoute) => void;
  replace: (route: AppRoute) => void;
  setResourceOptions: Dispatch<SetStateAction<ContextOption[]>>;
  setServiceOnline: Dispatch<SetStateAction<boolean | null>>;
}

export function PageOutlet({
  route,
  machine,
  target,
  navigate,
  replace,
  setResourceOptions,
  setServiceOnline,
}: PageOutletProps) {
  const { t } = useTranslation();
  let page: React.ReactNode = null;

  if (route.section === "home") {
    page = (
      <HomePage
        onNavigate={(target) =>
          navigate(
            target === "task-defs"
              ? defaultRoute("task-defs")
              : target === "tasks"
                ? { section: "runtime", view: "tasks" }
                : defaultRoute(target),
          )
        }
      />
    );
  } else if (route.section === "agent") {
    const view =
      route.view === "chat" || route.view === "task" ? route.view : "new";
    page = (
      <AgentWorkspace
        key={machine.id}
        view={view}
        resource={route.resource}
        target={target}
        navigate={navigate}
        replace={replace}
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  } else if (route.section === "runtime") {
    const view =
      route.view === "environment" || route.view === "resources"
        ? route.view
        : route.view === "task"
          ? "task"
          : "tasks";
    page = (
      <RuntimeWorkspace
        machine={machine}
        target={target}
        view={view}
        taskId={route.resource}
        onNavigate={(nextView, resource) =>
          navigate({ section: "runtime", view: nextView, resource })
        }
        onInterpretTask={(taskId) =>
          navigate({ section: "agent", view: "task", resource: taskId })
        }
        onOpenResearch={(taskType, taskId) =>
          navigate({
            section:
              taskType === "analysis" ? "factors" : (taskType as SectionId),
            view: "runs",
            resource: taskId,
          })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  } else if (route.section === "workspace") {
    page = (
      <WorkspaceBrowserPage
        key={target || "local"}
        target={target}
        machineId={machine.id}
        initialPath={route.resource}
        onConnection={setServiceOnline}
        onPathChange={(path) =>
          navigate({
            section: "workspace",
            view: "files",
            resource: path || undefined,
          })
        }
        onOptionsChange={setResourceOptions}
      />
    );
  } else if (route.section === "operations") {
    const definition = operationPages.find((page) => page.id === route.view);
    page = definition ? (
      <OperationPage
        key={`${target}:${definition.id}`}
        page={definition}
        target={target}
        initialResource={route.resource}
        onSelected={(resource) =>
          navigate({ ...route, resource: resource || undefined })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
        onOpenTask={(resource) =>
          navigate({ section: "runtime", view: "task", resource })
        }
      />
    ) : (
      <div className="empty-research">
        <p role="status">{t("operations.unavailable")}</p>
      </div>
    );
  } else if (route.section === "report" && route.resource) {
    page = (
      <ReportPage
        key={`${target}:${route.resource}`}
        taskId={route.resource}
        target={target}
        onOpenTask={(resource) =>
          navigate({ section: "runtime", view: "task", resource })
        }
      />
    );
  } else if (route.section === "compare") {
    page = (
      <StrategyComparePage
        target={target}
        initialTaskId={route.resource}
        onConnection={setServiceOnline}
      />
    );
  } else if (researchSections.has(route.section)) {
    const kind = route.section === "factors" ? "analysis" : route.section;
    page = (
      <ResearchPage
        key={`${kind}:${target || "local"}`}
        kind={kind as "analysis" | "backtest" | "etl" | "train" | "predict"}
        target={target}
        initialSelectedId={route.resource}
        onSelected={(resource) =>
          navigate({ section: route.section, view: "runs", resource })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
        onNavigate={(target: ResearchPageId | "runtime", resource?: string) =>
          navigate(
            target === "runtime"
              ? { section: "runtime", view: "task", resource }
              : {
                  section:
                    target === "factors" ? "factors" : (target as SectionId),
                  view: "runs",
                  resource,
                },
          )
        }
      />
    );
  } else if (route.section === "apis") {
    page = (
      <ApiWorkspace
        machine={machine}
        initialName={route.resource}
        onSelected={(resource) =>
          navigate({ section: "apis", view: "catalog", resource })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  } else if (route.section === "task-defs") {
    page = (
      <TaskDefinitionsPage
        key={machine.id}
        target={target}
        machineId={machine.id}
        onOpenTask={(resource) =>
          navigate({ section: "runtime", view: "task", resource })
        }
        initialName={route.resource}
        onSelected={(resource) =>
          navigate({ section: "task-defs", view: "catalog", resource })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  }

  return <Suspense fallback={<PageLoading />}>{page}</Suspense>;
}

function PageLoading() {
  const { t } = useTranslation();
  return <div className="loading-state tall">{t("shell.loading")}</div>;
}
