import {
  Activity,
  BarChart3,
  BrainCircuit,
  Cpu,
  Database,
  FileCode2,
  FlaskConical,
  Network,
  GitBranch,
  GitCompareArrows,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { AppRoute, SectionId } from "./routes";

export interface NavigationItem {
  id: string;
  route: AppRoute;
  icon: typeof Cpu;
  zh: string;
  en: string;
}

export interface NavigationGroup {
  id: "run" | "submit" | "research";
  zh: string;
  en: string;
  items: NavigationItem[];
}

export const navigationGroups: NavigationGroup[] = [
  {
    id: "run",
    zh: "运行",
    en: "Run",
    items: [
      {
        id: "tasks",
        route: { section: "runtime", view: "tasks" },
        icon: Activity,
        zh: "任务管理",
        en: "Task management",
      },
      {
        id: "resources",
        route: { section: "runtime", view: "resources" },
        icon: Cpu,
        zh: "机器资源",
        en: "Machine resources",
      },
      {
        id: "lineage",
        route: { section: "lineage", view: "runs" },
        icon: GitBranch,
        zh: "任务关系图",
        en: "Task graph",
      },
    ],
  },
  {
    id: "submit",
    zh: "提交",
    en: "Submit",
    items: [
      {
        id: "task-defs",
        route: { section: "task-defs", view: "catalog" },
        icon: FileCode2,
        zh: "提交任务",
        en: "Submit task",
      },
      {
        id: "apis",
        route: { section: "apis", view: "catalog" },
        icon: Network,
        zh: "API接口",
        en: "API interfaces",
      },
    ],
  },
  {
    id: "research",
    zh: "研究",
    en: "Research",
    items: [
      {
        id: "raw",
        route: { section: "raw", view: "files", resource: "tushare" },
        icon: Database,
        zh: "Tushare数据",
        en: "Tushare data",
      },
      {
        id: "etl",
        route: { section: "etl", view: "runs" },
        icon: Workflow,
        zh: "ETL",
        en: "ETL",
      },
      {
        id: "factors",
        route: { section: "factors", view: "runs" },
        icon: Sparkles,
        zh: "因子分析",
        en: "Factor analysis",
      },
      {
        id: "train",
        route: { section: "train", view: "runs" },
        icon: BrainCircuit,
        zh: "模型训练",
        en: "Model training",
      },
      {
        id: "predict",
        route: { section: "predict", view: "runs" },
        icon: FlaskConical,
        zh: "离线预测",
        en: "Offline prediction",
      },
      {
        id: "backtest",
        route: { section: "backtest", view: "runs" },
        icon: BarChart3,
        zh: "离线回测",
        en: "Offline backtest",
      },
      {
        id: "compare",
        route: { section: "compare", view: "strategies" },
        icon: GitCompareArrows,
        zh: "策略对比",
        en: "Strategy comparison",
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
        (route.section !== "runtime" || item.route.view === route.view),
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
