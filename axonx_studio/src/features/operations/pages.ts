import { Activity, Database } from "lucide-react";

export interface OperationPageDefinition {
  id: string;
  titleKey: string;
  icon: typeof Activity;
  reportKinds: readonly string[];
}

export const operationPages: readonly OperationPageDefinition[] = [
  {
    id: "online",
    titleKey: "onlineWorkbench.title",
    icon: Activity,
    reportKinds: ["online_pipeline", "online"],
  },
  {
    id: "comparison",
    titleKey: "operations.comparison",
    icon: Activity,
    reportKinds: ["compare_pipeline"],
  },
  {
    id: "data",
    titleKey: "operations.dataUpdate",
    icon: Database,
    reportKinds: ["data_update"],
  },
];
