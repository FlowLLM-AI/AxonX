import { useCallback, useEffect, useState } from "react";
import { AppShell } from "./app/AppShell";
import { useAppPreferences } from "./app/hooks/useAppPreferences";
import { useHashRoute } from "./app/hooks/useHashRoute";
import { useMachines } from "./app/hooks/useMachines";
import { useServiceStatus } from "./app/hooks/useServiceStatus";
import { useSidebar } from "./app/hooks/useSidebar";
import { PageOutlet } from "./app/PageOutlet";
import { parseHash } from "./app/routes";
import type { ContextOption } from "./app/types";
import { useAxonXWebMcp } from "./webmcp";

export default function App() {
  useAxonXWebMcp();
  const { language, setLanguage, theme, setTheme } = useAppPreferences();
  const { machineId, route, navigate } = useHashRoute();
  const navigateToMachine = useCallback(
    (nextMachineId: string) => {
      navigate(parseHash(window.location.hash).route, nextMachineId);
    },
    [navigate],
  );
  const { machines, selectedMachine, remoteIp } = useMachines(
    machineId,
    navigateToMachine,
  );
  const [serviceOnline, setServiceOnline] = useServiceStatus(remoteIp);
  const [resourceOptions, setResourceOptions] = useState<ContextOption[]>([]);
  const sidebar = useSidebar();

  useEffect(
    () => setResourceOptions([]),
    [machineId, route.section, route.view],
  );

  return (
    <AppShell
      route={route}
      language={language}
      setLanguage={setLanguage}
      theme={theme}
      setTheme={setTheme}
      serviceOnline={serviceOnline}
      machines={machines}
      selectedMachine={selectedMachine}
      remoteIp={remoteIp}
      resourceOptions={resourceOptions}
      sidebar={sidebar}
      navigate={navigate}
    >
      <PageOutlet
        route={route}
        language={language}
        machine={selectedMachine}
        remoteIp={remoteIp}
        navigate={navigate}
        setResourceOptions={setResourceOptions}
        setServiceOnline={setServiceOnline}
      />
    </AppShell>
  );
}
