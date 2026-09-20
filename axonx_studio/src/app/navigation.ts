import {
  Activity,
  BarChart3,
  BrainCircuit,
  Cpu,
  Database,
  FileCode2,
  FlaskConical,
  Network,
  GitCompareArrows,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { AppRoute, SectionId } from "./routes";

export interface NavigationItem {
  id: string;
  route: AppRoute;
  icon: typeof Cpu;
  labelKey: string;
}

export interface NavigationGroup {
  id: "run" | "submit" | "research";
  labelKey: string;
  items: NavigationItem[];
}

export const navigationGroups: NavigationGroup[] = [
  {
    id: "run",
    labelKey: "shell.groups.run",
    items: [
      {
        id: "tasks",
        route: { section: "runtime", view: "tasks" },
        icon: Activity,
        labelKey: "shell.navigation.tasks",
      },
      {
        id: "resources",
        route: { section: "runtime", view: "resources" },
        icon: Cpu,
        labelKey: "shell.navigation.resources",
      },
    ],
  },
  {
    id: "submit",
    labelKey: "shell.groups.submit",
    items: [
      {
        id: "task-defs",
        route: { section: "task-defs", view: "catalog" },
        icon: FileCode2,
        labelKey: "shell.navigation.taskDefs",
      },
      {
        id: "apis",
        route: { section: "apis", view: "catalog" },
        icon: Network,
        labelKey: "shell.navigation.apis",
      },
    ],
  },
  {
    id: "research",
    labelKey: "shell.groups.research",
    items: [
      {
        id: "raw",
        route: { section: "raw", view: "files", resource: "tushare" },
        icon: Database,
        labelKey: "shell.navigation.raw",
      },
      {
        id: "etl",
        route: { section: "etl", view: "runs" },
        icon: Workflow,
        labelKey: "shell.navigation.etl",
      },
      {
        id: "factors",
        route: { section: "factors", view: "runs" },
        icon: Sparkles,
        labelKey: "shell.navigation.factors",
      },
      {
        id: "train",
        route: { section: "train", view: "runs" },
        icon: BrainCircuit,
        labelKey: "shell.navigation.train",
      },
      {
        id: "predict",
        route: { section: "predict", view: "runs" },
        icon: FlaskConical,
        labelKey: "shell.navigation.predict",
      },
      {
        id: "backtest",
        route: { section: "backtest", view: "runs" },
        icon: BarChart3,
        labelKey: "shell.navigation.backtest",
      },
      {
        id: "compare",
        route: { section: "compare", view: "strategies" },
        icon: GitCompareArrows,
        labelKey: "shell.navigation.compare",
      },
    ],
  },
];

export const navigationItems = navigationGroups.flatMap((group) => group.items);

export function navigationItemForRoute(route: AppRoute): NavigationItem {
  return (
    navigationItems.find(
      (item) =>
        item.route.section === route.section &&
        (route.section !== "runtime" ||
          item.route.view === route.view ||
          (item.id === "tasks" &&
            ["overview", "logs", "relations"].includes(route.view || ""))),
    ) || navigationItems[0]
  );
}

export const researchSections = new Set<SectionId>([
  "etl",
  "factors",
  "train",
  "predict",
  "backtest",
]);
