import { lazy, Suspense } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ResearchPageId } from "../features/research/types";
import type { ContextOption } from "./types";
import { useTranslation } from "react-i18next";
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
  machine: MachineNode;
  remoteIp?: string;
  navigate: (route: AppRoute) => void;
  setResourceOptions: Dispatch<SetStateAction<ContextOption[]>>;
  setServiceOnline: Dispatch<SetStateAction<boolean | null>>;
}

export function PageOutlet({
  route,
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
      route.view === "environment" || route.view === "resources"
        ? route.view
        : ["overview", "logs", "relations"].includes(route.view || "")
          ? (route.view as "overview" | "logs" | "relations")
          : "tasks";
    page = (
      <RuntimeWorkspace
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
  } else if (route.section === "compare") {
    page = (
      <StrategyComparePage
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
              ? { section: "runtime", view: "overview", resource }
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
      <SubmitPage
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
    page = <UnknownPage section={route.section} />;
  }

  return <Suspense fallback={<PageLoading />}>{page}</Suspense>;
}

function PageLoading() {
  const { t } = useTranslation();
  return <div className="loading-state tall">{t("shell.loading")}</div>;
}

function UnknownPage({ section }: { section: string }) {
  const { t } = useTranslation();
  return <div className="data-gap">{t("shell.unknownPage", { section })}</div>;
}
