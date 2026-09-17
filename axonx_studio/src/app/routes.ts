export const sectionIds = [
  "home",
  "runtime",
  "apis",
  "task-defs",
  "raw",
  "lineage",
  "etl",
  "factors",
  "train",
  "predict",
  "backtest",
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

export function parseHash(hash: string): AppLocation {
  const parts = hash.replace(/^#/, "").split("/").filter(Boolean);
  const machineScoped = parts[0] === "m";
  const machineId =
    machineScoped && parts[1] ? decodeURIComponent(parts[1]) : "local";
  const [candidate, view, ...resourceParts] = machineScoped
    ? parts.slice(2)
    : [];
  const section = sectionSet.has(candidate)
    ? (candidate as SectionId)
    : "runtime";
  const validSection = sectionSet.has(candidate);

  return {
    machineId,
    route: {
      section,
      view: validSection ? view || defaultRoute(section).view : "tasks",
      resource:
        validSection && resourceParts.length
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
  const view =
    section === "home"
      ? "overview"
      : section === "runtime"
        ? "tasks"
        : section === "raw"
          ? "files"
          : section === "apis" || section === "task-defs"
            ? "catalog"
            : "runs";

  return {
    section,
    view,
    resource: section === "raw" ? "tushare" : undefined,
  };
}
