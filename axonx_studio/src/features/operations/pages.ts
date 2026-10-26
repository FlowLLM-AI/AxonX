import type { TaskCategory } from "../../shared/api/contracts";

export interface OperationPageDefinition {
  id: string;
  titleKey: string;
  view: "tasks" | "pipeline";
  category: TaskCategory;
}

export const operationPages: readonly OperationPageDefinition[] = [
  {
    id: "online",
    titleKey: "onlineWorkbench.title",
    view: "pipeline",
    category: "online_prediction",
  },
  {
    id: "comparison",
    titleKey: "operations.comparison",
    view: "pipeline",
    category: "comparison",
  },
  {
    id: "data",
    titleKey: "operations.dataUpdate",
    view: "tasks",
    category: "data_update",
  },
];
