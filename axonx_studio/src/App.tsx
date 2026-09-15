import { useEffect, useMemo, useState } from "react";
import {
  Activity, BarChart3, Blocks, BrainCircuit, ChevronDown, ChevronLeft,
  ChevronRight, CircleGauge, Cpu, Database, Files, Home, Languages,
  Menu, Moon, PackageOpen, PanelLeftClose, PanelLeftOpen, Play, Plug, Send, Server,
  Sun, TableProperties, Workflow, X,
} from "lucide-react";
import { API_URL, listMachineOptions, machineHost } from "./api";
import { t } from "./i18n";
import { MachinesPage } from "./MachinesPage";
import { SubmitPage } from "./SubmitPage";
import { TaskDetailPage } from "./TaskDetailPage";
import { TasksPage } from "./TasksPage";
import { WorkspaceBrowserPage } from "./WorkspaceBrowserPage";
import { ResearchPage } from "./ResearchPages";
import { ComingSoonPage, HomePage, JobCatalogPage, PluginsPage, TaskCatalogPage } from "./WorkspacePages";
import type { Language, MachineNode, PageId, ThemePreference } from "./types";
import { useAxonXWebMcp } from "./webmcp";

type NavItem = { id: PageId; icon: typeof Cpu; ready?: boolean };
type NavGroup = { id: string; label: { zh: string; en: string }; icon: typeof Cpu; items: NavItem[] };

const groups: NavGroup[] = [
  { id: "runtime", label: { zh: "运行中心", en: "Operations" }, icon: CircleGauge, items: [
    { id: "machines", icon: Cpu, ready: true }, { id: "tasks", icon: Activity, ready: true }, { id: "submit", icon: Send, ready: true }, { id: "files", icon: Files, ready: true },
  ] },
  { id: "data", label: { zh: "数据中心", en: "Data" }, icon: Database, items: [
    { id: "etl", icon: TableProperties, ready: true }, { id: "factors", icon: Workflow, ready: true },
  ] },
  { id: "model", label: { zh: "模型中心", en: "Models" }, icon: BrainCircuit, items: [
    { id: "training", icon: BrainCircuit, ready: true }, { id: "predict", icon: Play, ready: true },
  ] },
  { id: "strategy", label: { zh: "策略与回测", en: "Strategy & Backtest" }, icon: BarChart3, items: [
    { id: "backtest", icon: BarChart3, ready: true },
  ] },
  { id: "extensions", label: { zh: "扩展中心", en: "Extensions" }, icon: Plug, items: [
    { id: "plugins", icon: PackageOpen, ready: true }, { id: "jobs", icon: Workflow, ready: true }, { id: "taskCatalog", icon: Activity, ready: true }, { id: "components", icon: Blocks },
  ] },
];

const allPages = new Set<PageId>(["home", ...groups.flatMap((group) => group.items.map((item) => item.id))]);
const legacyPages: Record<string, PageId> = { rawData: "files", tushare: "files", datasets: "etl", prediction: "predict", inference: "predict", models: "training", reports: "backtest" };
const initialPage = (): PageId => {
  const value = window.location.hash.slice(1);
  if (value.startsWith("tasks/")) return "tasks";
  return legacyPages[value] || (allPages.has(value as PageId) ? value as PageId : "home");
};
const initialTaskId = () => {
  const value = window.location.hash.slice(1);
  if (!value.startsWith("tasks/")) return "";
  try { return decodeURIComponent(value.slice("tasks/".length)); }
  catch { return ""; }
};

export default function App() {
  useAxonXWebMcp();
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem("axonx-language") === "en" ? "en" : "zh");
  const [theme, setTheme] = useState<ThemePreference>(() => {
    const saved = localStorage.getItem("axonx-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });
  const [page, setPageState] = useState<PageId>(initialPage);
  const [taskDetailId, setTaskDetailId] = useState(initialTaskId);
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("axonx-sidebar") === "collapsed");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState(() => new Set(["runtime"]));
  const [machines, setMachines] = useState<MachineNode[]>([{ id: "local", address: "localhost", isLocal: true, healthy: true }]);
  const [machineId, setMachineId] = useState(() => localStorage.getItem("axonx-machine") || "local");
  const [machinesLoaded, setMachinesLoaded] = useState(false);
  const [machinesLoading, setMachinesLoading] = useState(false);
  const text = t(language);
  const selectedMachine = machines.find((item) => item.id === machineId) || machines[0];
  const remoteIp = selectedMachine?.isLocal ? undefined : machineHost(selectedMachine.address);

  const setPage = (next: PageId) => {
    window.location.hash = next; setPageState(next); setTaskDetailId(""); setMobileOpen(false);
  };
  const openTask = (taskId: string) => {
    window.location.hash = `tasks/${encodeURIComponent(taskId)}`; setPageState("tasks"); setTaskDetailId(taskId); setMobileOpen(false);
  };
  const selectMachine = (nextMachineId: string) => {
    if (nextMachineId === machineId) return;
    setMachineId(nextMachineId);
    if (taskDetailId) setPage("tasks");
  };

  const loadMachines = async () => {
    if (machinesLoaded || machinesLoading) return;
    setMachinesLoading(true);
    try {
      const result = await listMachineOptions();
      setMachines(result);
      setMachineId((current) => result.some((item) => item.id === current) ? current : "local");
      setMachinesLoaded(true); setServiceOnline(true);
    } catch { setServiceOnline(false); }
    finally { setMachinesLoading(false); }
  };

  useEffect(() => {
    const onHash = () => { setPageState(initialPage()); setTaskDetailId(initialTaskId()); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { localStorage.setItem("axonx-language", language); document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; document.title = text.consoleTitle; }, [language, text.consoleTitle]);
  useEffect(() => { localStorage.setItem("axonx-machine", machineId); }, [machineId]);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.dataset.theme = theme === "dark" || (theme === "system" && media.matches) ? "dark" : "light";
    localStorage.setItem("axonx-theme", theme); apply(); media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    let alive = true;
    const checkService = () => fetch(`${API_URL}/health`).then((response) => response.ok ? response.json() : null).then((data) => alive && setServiceOnline(data?.running === true)).catch(() => alive && setServiceOnline(false));
    void checkService();
    const timer = window.setInterval(checkService, 15_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const content = useMemo(() => {
    if (page === "home") return <HomePage language={language} remoteIp={remoteIp} machine={selectedMachine} onConnection={setServiceOnline} onNavigate={setPage} />;
    if (page === "machines") return <MachinesPage language={language} onConnection={setServiceOnline} />;
    if (page === "tasks" && taskDetailId) return <TaskDetailPage taskId={taskDetailId} language={language} remoteIp={remoteIp} onBack={() => setPage("tasks")} onConnection={setServiceOnline} />;
    if (page === "tasks") return <TasksPage language={language} remoteIp={remoteIp} onSubmit={() => setPage("submit")} onOpenTask={openTask} onConnection={setServiceOnline} />;
    if (page === "submit") return <SubmitPage language={language} remoteIp={remoteIp} onViewTasks={() => setPage("tasks")} onConnection={setServiceOnline} />;
    if (page === "files") return <WorkspaceBrowserPage language={language} remoteIp={remoteIp} onConnection={setServiceOnline} />;
    if (page === "etl" || page === "factors" || page === "training" || page === "predict" || page === "backtest") return <ResearchPage kind={page === "factors" ? "analysis" : page} language={language} remoteIp={remoteIp} onConnection={setServiceOnline} onNavigate={setPage} />;
    if (page === "plugins") return <PluginsPage language={language} remoteIp={remoteIp} onConnection={setServiceOnline} />;
    if (page === "jobs") return <JobCatalogPage language={language} machine={selectedMachine} onConnection={setServiceOnline} />;
    if (page === "taskCatalog") return <TaskCatalogPage language={language} remoteIp={remoteIp} onConnection={setServiceOnline} onSubmit={() => setPage("submit")} />;
    return <ComingSoonPage page={page} language={language} />;
  }, [page, taskDetailId, language, remoteIp, selectedMachine]);

  const toggleSidebar = () => setSidebarCollapsed((value) => {
    localStorage.setItem("axonx-sidebar", value ? "expanded" : "collapsed"); return !value;
  });

  return <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
    <aside className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <header className="sidebar-brand">
        <button className="brand" onClick={() => setPage("home")} aria-label={text.consoleTitle}>
          <img className="brand-icon" src="/axonx-icon.svg" alt="" width="40" height="40" />
          <span className="brand-copy"><strong>{text.consoleTitle}</strong><small className={serviceOnline === true ? "online" : serviceOnline === false ? "offline" : "checking"}><i />{serviceOnline === true ? text.serviceOnline : serviceOnline === false ? text.serviceOffline : text.serviceChecking}</small></span>
        </button>
        <button className="sidebar-toggle desktop-only" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>{sidebarCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}</button>
        <button className="sidebar-toggle mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X /></button>
      </header>
      <nav className="side-nav" aria-label="Main navigation">
        <button className={`nav-home ${page === "home" ? "active" : ""}`} onClick={() => setPage("home")} title={text.pages.home}><Home /><span>{text.pages.home}</span></button>
        {groups.map((group) => {
          const GroupIcon = group.icon; const open = openGroups.has(group.id); const groupActive = group.items.some((item) => item.id === page);
          return <section className={`nav-group ${groupActive ? "has-active" : ""}`} key={group.id}>
            <button className="nav-group-button" onClick={() => setOpenGroups((current) => { const next = new Set(current); if (next.has(group.id)) next.delete(group.id); else next.add(group.id); return next; })} title={group.label[language]}><GroupIcon /><span>{group.label[language]}</span><ChevronDown className={open ? "open" : ""} /></button>
            {open && <div className="nav-children">{group.items.map(({ id, icon: Icon, ready }) => <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)} title={text.pages[id]}><Icon /><span>{text.pages[id]}</span>{!ready && <i>{language === "zh" ? "待开发" : "Planned"}</i>}</button>)}</div>}
          </section>;
        })}
      </nav>
      <footer className="sidebar-footer"><button onClick={toggleSidebar}>{sidebarCollapsed ? <ChevronRight /> : <><ChevronLeft /><span>{language === "zh" ? "收起侧栏" : "Collapse"}</span></>}</button></footer>
    </aside>
    {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <div className="app-main">
      <header className="topbar">
        <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></button>
        <div className="breadcrumb"><span>AXONX</span><ChevronRight />{taskDetailId ? text.taskDetails : text.pages[page]}</div>
        <div className="header-actions">
          <div className="machine-picker" onMouseEnter={() => void loadMachines()} onFocus={() => void loadMachines()}>
            <button className="machine-trigger topbar-control"><Server /><span><small>{text.currentMachine}</small><strong>{selectedMachine?.isLocal ? text.localNode : selectedMachine?.address}</strong></span><ChevronDown /></button>
            <div className="machine-menu">{machinesLoading && <p>{language === "zh" ? "读取机器列表…" : "Loading machines…"}</p>}{machines.map((machine) => <button key={machine.id} className={machine.id === selectedMachine?.id ? "active" : ""} onClick={() => selectMachine(machine.id)}><i className={machine.healthy ? "online" : "offline"} /><span>{machine.isLocal ? (language === "zh" ? "本机" : "Local") : machine.address}</span>{machine.id === selectedMachine?.id && <span>✓</span>}</button>)}</div>
          </div>
          <button className="topbar-control language-button" onClick={() => setLanguage(language === "zh" ? "en" : "zh")} title={text.switchLanguage}><Languages /><span>{language === "zh" ? "EN" : "中文"}</span></button>
          <div className="theme-picker"><button className="topbar-control theme-trigger" aria-label={text.appearance}>{theme === "light" ? <Sun /> : theme === "dark" ? <Moon /> : <span className="system-icon">◐</span>}<span>{text[theme]}</span><ChevronDown /></button><div className="theme-menu">{(["system", "light", "dark"] as ThemePreference[]).map((value) => <button key={value} className={theme === value ? "active" : ""} onClick={() => setTheme(value)}>{text[value]}</button>)}</div></div>
          <a className="topbar-control github-link" href="https://github.com/FlowLLM-AI/AxonX" target="_blank" rel="noreferrer" aria-label={text.openGithub} title={text.openGithub}><GitHubMark /></a>
        </div>
      </header>
      <main>{content}</main>
    </div>
  </div>;
}

function GitHubMark() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.24c-3.23.7-3.91-1.37-3.91-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.26 3.38.96.1-.75.41-1.26.74-1.55-2.58-.29-5.29-1.29-5.29-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.16 1.18a10.96 10.96 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.58.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.72 5.39-5.31 5.68.42.36.79 1.07.79 2.16v3.26c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" /></svg>;
}
