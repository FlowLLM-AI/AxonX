export interface OperationPageDefinition {
  id: string;
  titleKey: string;
  view: "tasks" | "pipeline";
  reportKinds: readonly string[];
}

export const operationPages: readonly OperationPageDefinition[] = [
  {
    id: "online",
    titleKey: "onlineWorkbench.title",
    view: "pipeline",
    reportKinds: ["online_pipeline", "online"],
  },
  {
    id: "comparison",
    titleKey: "operations.comparison",
    view: "pipeline",
    reportKinds: ["compare_pipeline"],
  },
  {
    id: "data",
    titleKey: "operations.dataUpdate",
    view: "tasks",
    reportKinds: ["data_update"],
  },
];
