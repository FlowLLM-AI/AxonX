import { AppShell } from "./app/AppShell";
import { PageOutlet } from "./app/PageOutlet";
import { useStudio } from "./app/useStudio";
import { useAxonXWebMcp } from "./webmcp";

export default function App() {
  useAxonXWebMcp();
  const studio = useStudio();

  return (
    <AppShell
      route={studio.route}
      theme={studio.theme}
      setTheme={studio.setTheme}
      serviceOnline={studio.serviceOnline}
      authRequired={studio.authRequired}
      authTokenConfigured={studio.authTokenConfigured}
      setAuthToken={studio.setAuthToken}
      machines={studio.machines}
      selectedMachine={studio.selectedMachine}
      remoteIp={studio.remoteIp}
      resourceOptions={studio.resourceOptions}
      sidebar={studio.sidebar}
      navigate={studio.navigate}
    >
      <PageOutlet
        key={studio.authRevision}
        route={studio.route}
        machine={studio.selectedMachine}
        remoteIp={studio.remoteIp}
        navigate={studio.navigate}
        replace={studio.replace}
        setResourceOptions={studio.setResourceOptions}
        setServiceOnline={studio.setServiceOnline}
      />
    </AppShell>
  );
}
