import { AppShell } from "./app/AppShell";
import { PageOutlet } from "./app/PageOutlet";
import { useStudio } from "./app/useStudio";
import { useAxonXWebMcp } from "./webmcp";
import { TaskExecutionMonitor } from "./features/tasks/TaskExecution";

export default function App() {
  useAxonXWebMcp();
  const studio = useStudio();

  return (
    <AppShell
      route={studio.route}
      theme={studio.theme}
      setTheme={studio.setTheme}
      serviceOnline={studio.serviceOnline}
      backendVersion={studio.backendVersion}
      authRequired={studio.authRequired}
      authTokenConfigured={studio.authTokenConfigured}
      setAuthToken={studio.setAuthToken}
      machines={studio.machines}
      selectedMachine={studio.selectedMachine}
      target={studio.target}
      resourceOptions={studio.resourceOptions}
      sidebar={studio.sidebar}
      navigate={studio.navigate}
    >
      <TaskExecutionMonitor
        onOpenTask={(run) =>
          studio.navigate(
            { section: "runtime", view: "task", resource: run.taskId },
            run.machineId,
          )
        }
      />
      <PageOutlet
        key={`${studio.authRevision}:${studio.selectedMachine.id}`}
        route={studio.route}
        machine={studio.selectedMachine}
        target={studio.target}
        navigate={studio.navigate}
        replace={studio.replace}
        setResourceOptions={studio.setResourceOptions}
        setServiceOnline={studio.setServiceOnline}
      />
    </AppShell>
  );
}
