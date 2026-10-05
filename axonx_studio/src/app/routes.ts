export const sectionIds = [
  "home",
  "runtime",
  "agent",
  "apis",
  "task-defs",
  "workspace",
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
  workspace: "files",
  etl: "runs",
  factors: "runs",
  train: "runs",
  predict: "runs",
  backtest: "runs",
  compare: "strategies",
};

export function parseHash(hash: string): AppLocation {
  const [machineId = "local", candidate = "home", view, resource] = hash
    .replace(/^#/, "")
    .split("/")
    .filter(Boolean);
  const valid = sectionSet.has(candidate);
  const section: SectionId = valid ? (candidate as SectionId) : "home";

  return {
    machineId: decodeURIComponent(machineId),
    route: {
      section,
      view: valid && view ? view : defaultViews[section],
      resource: valid && resource ? decodeURIComponent(resource) : undefined,
    },
  };
}

export function routeHash(machineId: string, route: AppRoute): string {
  const path = [
    route.section,
    route.view || defaultViews[route.section],
    route.resource ? encodeURIComponent(route.resource) : "",
  ]
    .filter(Boolean)
    .join("/");

  return `#${encodeURIComponent(machineId).replace(/%3A/g, ":")}/${path}`;
}

export function defaultRoute(section: SectionId): AppRoute {
  return {
    section,
    view: defaultViews[section],
    resource: undefined,
  };
}
