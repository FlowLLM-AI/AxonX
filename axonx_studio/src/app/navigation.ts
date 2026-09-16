import {
  Activity,
  BarChart3,
  BrainCircuit,
  Cpu,
  Database,
  FileCode2,
  FlaskConical,
  Home,
  Network,
  GitBranch,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { SectionId } from "./routes";

export interface NavigationItem {
  id: SectionId;
  icon: typeof Cpu;
  zh: string;
  en: string;
}

export const navigationItems: NavigationItem[] = [
  { id: "home", icon: Home, zh: "首页", en: "Home" },
  { id: "runtime", icon: Activity, zh: "运行管理", en: "Runs" },
  { id: "apis", icon: Network, zh: "API接口", en: "API interfaces" },
  { id: "task-defs", icon: FileCode2, zh: "提交Task", en: "Submit Task" },
  { id: "raw", icon: Database, zh: "Tushare数据", en: "Tushare data" },
  { id: "lineage", icon: GitBranch, zh: "任务关系图", en: "Task graph" },
  { id: "etl", icon: Workflow, zh: "ETL", en: "ETL" },
  { id: "factors", icon: Sparkles, zh: "因子分析", en: "Factor analysis" },
  { id: "training", icon: BrainCircuit, zh: "模型训练", en: "Model training" },
  {
    id: "predict",
    icon: FlaskConical,
    zh: "离线预测",
    en: "Offline prediction",
  },
  { id: "backtest", icon: BarChart3, zh: "离线回测", en: "Offline backtest" },
];

export const researchSections = new Set<SectionId>([
  "etl",
  "factors",
  "training",
  "predict",
  "backtest",
]);
