export const sectionIds = [
  "home",
  "runtime",
  "agent",
  "apis",
  "task-defs",
  "raw",
  "etl",
  "factors",
  "train",
  "predict",
  "backtest",
  "compare",
] as const;

export type SectionId = (typeof sectionIds)[number];

export interface AppRoute {
  section: SectionId;
  view?: string;
  resource?: string;
}

export interface AppLocation {
  machineId: string;
  route: AppRoute;
}

const sectionSet = new Set<string>(sectionIds);
const defaultViews: Record<SectionId, string> = {
  home: "overview",
  runtime: "tasks",
  agent: "new",
  apis: "catalog",
  "task-defs": "catalog",
  raw: "files",
  etl: "runs",
  factors: "runs",
  train: "runs",
  predict: "runs",
  backtest: "runs",
  compare: "strategies",
};

export function parseHash(hash: string): AppLocation {
  const parts = hash.replace(/^#/, "").split("/").filter(Boolean);
  const machineScoped = parts[0] === "m";
  const machineId =
    machineScoped && parts[1] ? decodeURIComponent(parts[1]) : "local";
  const [candidate, view, ...resourceParts] = machineScoped
    ? parts.slice(2)
    : [];
  const section: SectionId = sectionSet.has(candidate)
    ? (candidate as SectionId)
    : "runtime";
  const valid = sectionSet.has(candidate);

  return {
    machineId,
    route: {
      section,
      view: valid ? view || defaultViews[section] : defaultViews.runtime,
      resource:
        valid && resourceParts.length
          ? decodeURIComponent(resourceParts.join("/"))
          : undefined,
    },
  };
}

export function routeHash(machineId: string, route: AppRoute): string {
  const path = [
    route.section,
    route.view,
    route.resource ? encodeURIComponent(route.resource) : "",
  ]
    .filter(Boolean)
    .join("/");

  return `#m/${encodeURIComponent(machineId)}/${path}`;
}

export function defaultRoute(section: SectionId): AppRoute {
  return {
    section,
    view: defaultViews[section],
    resource: section === "raw" ? "tushare" : undefined,
  };
}
