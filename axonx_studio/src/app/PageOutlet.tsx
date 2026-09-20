import { lazy, Suspense } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ResearchPageId } from "../features/research/types";
import type { ContextOption, Language } from "./types";
import type { MachineNode } from "../features/machines/types";
import { researchSections } from "./navigation";
import { defaultRoute } from "./routes";
import type { AppRoute, SectionId } from "./routes";

const HomePage = lazy(() =>
  import("../features/HomePage").then((module) => ({
    default: module.HomePage,
  })),
);
const RuntimeWorkspace = lazy(() =>
  import("../features/runtime/RuntimeWorkspace").then((module) => ({
    default: module.RuntimeWorkspace,
  })),
);
const TushareBrowserPage = lazy(() =>
  import("../features/workspace/TushareBrowserPage").then((module) => ({
    default: module.TushareBrowserPage,
  })),
);
const ResearchPage = lazy(() =>
  import("../features/research/ResearchPage").then((module) => ({
    default: module.ResearchPage,
  })),
);
const StrategyComparePage = lazy(() =>
  import("../features/research/compare/StrategyComparePage").then((module) => ({
    default: module.StrategyComparePage,
  })),
);
const TaskGraphPage = lazy(() =>
  import("../features/task-graph/TaskGraphPage").then((module) => ({
    default: module.TaskGraphPage,
  })),
);
const ApiWorkspace = lazy(() =>
  import("../features/api-catalog/ApiWorkspace").then((module) => ({
    default: module.ApiWorkspace,
  })),
);
const SubmitPage = lazy(() =>
  import("../features/task-submit/SubmitPage").then((module) => ({
    default: module.SubmitPage,
  })),
);

interface PageOutletProps {
  route: AppRoute;
  language: Language;
  machine: MachineNode;
  remoteIp?: string;
  navigate: (route: AppRoute) => void;
  setResourceOptions: Dispatch<SetStateAction<ContextOption[]>>;
  setServiceOnline: Dispatch<SetStateAction<boolean | null>>;
}

export function PageOutlet({
  route,
  language,
  machine,
  remoteIp,
  navigate,
  setResourceOptions,
  setServiceOnline,
}: PageOutletProps) {
  let page: React.ReactNode;

  if (route.section === "home") {
    page = (
      <HomePage
        language={language}
        onNavigate={(target) =>
          navigate(
            target === "submit"
              ? defaultRoute("task-defs")
              : target === "tasks"
                ? { section: "runtime", view: "tasks" }
                : defaultRoute(target),
          )
        }
      />
    );
  } else if (route.section === "runtime") {
    const view =
      route.view === "tasks"
        ? "tasks"
        : route.view === "environment"
          ? "environment"
          : "resources";
    page = (
      <RuntimeWorkspace
        language={language}
        machine={machine}
        remoteIp={remoteIp}
        view={view}
        taskId={route.resource}
        onNavigate={(nextView, resource) =>
          navigate({ section: "runtime", view: nextView, resource })
        }
        onSubmit={() => navigate(defaultRoute("task-defs"))}
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  } else if (route.section === "raw") {
    page = (
      <TushareBrowserPage
        language={language}
        remoteIp={remoteIp}
        initialPath={route.resource}
        onConnection={setServiceOnline}
        onPathChange={(path) =>
          navigate({
            section: "raw",
            view: "files",
            resource: path || undefined,
          })
        }
        onOptionsChange={setResourceOptions}
      />
    );
  } else if (route.section === "lineage") {
    page = (
      <TaskGraphPage
        language={language}
        remoteIp={remoteIp}
        selectedId={route.resource}
        onSelect={(resource) =>
          navigate({ section: "lineage", view: "runs", resource })
        }
        onNavigate={(section, resource) =>
          navigate({ section, view: "runs", resource })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
      />
    );
  } else if (route.section === "compare") {
    page = (
      <StrategyComparePage
        language={language}
        remoteIp={remoteIp}
        initialTaskId={route.resource}
        onConnection={setServiceOnline}
      />
    );
  } else if (researchSections.has(route.section)) {
    const kind = route.section === "factors" ? "analysis" : route.section;
    page = (
      <ResearchPage
        key={`${kind}:${remoteIp || "local"}`}
        kind={kind as "analysis" | "backtest" | "etl" | "train" | "predict"}
        language={language}
        remoteIp={remoteIp}
        initialSelectedId={route.resource}
        onSelected={(resource) =>
          navigate({ section: route.section, view: "runs", resource })
        }
        onOptionsChange={setResourceOptions}
        onConnection={setServiceOnline}
        onNavigate={(target: ResearchPageId | "runtime", resource?: string) =>
          navigate(
            target === "runtime"
              ? { section: "runtime", view: "tasks", resource }
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
        language={language}
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
      <SubmitPage
        language={language}
        remoteIp={remoteIp}
        initialName={route.resource}
        onSelected={(resource) =>
          navigate({ section: "task-defs", view: "catalog", resource })
        }
        onOptionsChange={setResourceOptions}
        onViewTasks={() => navigate({ section: "runtime", view: "tasks" })}
        onConnection={setServiceOnline}
      />
    );
  } else {
    page = <div className="data-gap">Unknown page: {route.section}</div>;
  }

  return (
    <Suspense fallback={<div className="loading-state tall">Loading…</div>}>
      {page}
    </Suspense>
  );
}
