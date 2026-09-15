import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  Activity, BarChart3, BrainCircuit, ChevronDown, ChevronRight, Cpu, Database,
  FileCode2, FlaskConical, Home, Languages, Menu, Moon, Network, PanelLeftClose,
  PanelLeftOpen, Sparkles, Sun, Workflow,
} from "lucide-react";
import { listMachineOptions, machineHost, machineStatus } from "./api";
import { ApiWorkspace } from "./ApiWorkspace";
import { t } from "./i18n";
import { ResearchPage } from "./ResearchPages";
import { RailResizer } from "./RailResizer";
import { RuntimeWorkspace } from "./RuntimeWorkspace";
import { SubmitPage } from "./SubmitPage";
import { TushareBrowserPage } from "./TushareBrowserPage";
import type { ContextOption, Language, MachineNode, PageId, ThemePreference } from "./types";
import { HomePage } from "./WorkspacePages";
import { useAxonXWebMcp } from "./webmcp";

type SectionId = "home" | "runtime" | "apis" | "task-defs" | "raw" | "etl" | "factors" | "training" | "predict" | "backtest";
type Route = { section: SectionId; view?: string; resource?: string };
type LocationState = { machineId: string; route: Route };

const sections: { id: SectionId; icon: typeof Cpu; zh: string; en: string }[] = [
  { id: "home", icon: Home, zh: "首页", en: "Home" },
  { id: "runtime", icon: Activity, zh: "运行管理", en: "Runs" },
  { id: "apis", icon: Network, zh: "API接口", en: "API interfaces" },
  { id: "task-defs", icon: FileCode2, zh: "提交Task", en: "Submit Task" },
  { id: "raw", icon: Database, zh: "Tushare数据", en: "Tushare data" },
  { id: "etl", icon: Workflow, zh: "ETL", en: "ETL" },
  { id: "factors", icon: Sparkles, zh: "因子分析", en: "Factor analysis" },
  { id: "training", icon: BrainCircuit, zh: "模型训练", en: "Model training" },
  { id: "predict", icon: FlaskConical, zh: "离线预测", en: "Offline prediction" },
  { id: "backtest", icon: BarChart3, zh: "离线回测", en: "Offline backtest" },
];

function parseLocation(): LocationState {
  const parts = window.location.hash.slice(1).split("/").filter(Boolean);
  const scoped = parts[0] === "m";
  const machineId = scoped && parts[1] ? decodeURIComponent(parts[1]) : "local";
  const [section, view, ...rest] = scoped ? parts.slice(2) : [];
  const valid = sections.some((item) => item.id === section);
  return { machineId, route: { section: valid ? section as SectionId : "home", view: valid ? view : "overview", resource: rest.length ? decodeURIComponent(rest.join("/")) : undefined } };
}

function routeHref(machineId: string, route: Route) {
  return `#m/${encodeURIComponent(machineId)}/${[route.section, route.view, route.resource ? encodeURIComponent(route.resource) : ""].filter(Boolean).join("/")}`;
}

function defaultRoute(section: SectionId): Route {
  return { section, view: section === "home" ? "overview" : section === "runtime" ? "resources" : section === "raw" ? "files" : section === "apis" || section === "task-defs" ? "catalog" : "runs", resource: section === "raw" ? "tushare" : undefined };
}

export default function App() {
  useAxonXWebMcp();
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem("axonx-language") === "en" ? "en" : "zh");
  const [theme, setTheme] = useState<ThemePreference>(() => {
    const saved = localStorage.getItem("axonx-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });
  const [route, setRoute] = useState<Route>(() => parseLocation().route);
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("axonx-sidebar") === "collapsed");
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = Number(localStorage.getItem("axonx-sidebar-width"));
    return saved >= 190 && saved <= 360 ? saved : 248;
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [machines, setMachines] = useState<MachineNode[]>([{ id: "local", address: "localhost", isLocal: true, healthy: true }]);
  const [machineId, setMachineId] = useState(() => parseLocation().machineId || localStorage.getItem("axonx-machine") || "local");
  const [machinesLoaded, setMachinesLoaded] = useState(false);
  const [machinesLoading, setMachinesLoading] = useState(false);
  const [resourceOptions, setResourceOptions] = useState<ContextOption[]>([]);
  const text = t(language);
  const selectedMachine = machines.find((item) => item.id === machineId) || machines[0];
  const remoteIp = selectedMachine?.isLocal ? undefined : machineHost(selectedMachine.address);
  const section = sections.find((item) => item.id === route.section) || sections[0];
  const sectionLabel = section[language];

  const navigate = useCallback((next: Route) => {
    window.location.hash = routeHref(machineId, next);
    setRoute(next);
    setMobileOpen(false);
  }, [machineId]);

  const loadMachines = useCallback(async () => {
    if (machinesLoaded || machinesLoading) return;
    setMachinesLoading(true);
    try {
      const result = await listMachineOptions();
      setMachines(result);
      setMachineId((current) => result.some((item) => item.id === current) ? current : "local");
      setMachinesLoaded(true); setServiceOnline(true);
    } catch { setServiceOnline(false); }
    finally { setMachinesLoading(false); }
  }, [machinesLoaded, machinesLoading]);

  useEffect(() => {
    if (!window.location.hash) window.location.hash = "m/local/home/overview";
    const onHash = () => { const location = parseLocation(); setRoute(location.route); setMachineId(location.machineId); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { void loadMachines(); }, [loadMachines]);
  useEffect(() => { localStorage.setItem("axonx-language", language); document.documentElement.lang = language === "zh" ? "zh-CN" : "en"; document.title = "AxonX Studio"; }, [language]);
  useEffect(() => { localStorage.setItem("axonx-machine", machineId); }, [machineId]);
  useEffect(() => {
    let alive = true;
    const check = () => machineStatus(remoteIp).then(() => { if (alive) setServiceOnline(true); }).catch(() => { if (alive) setServiceOnline(false); });
    void check(); const timer = window.setInterval(check, 15_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [remoteIp]);
  useEffect(() => { setResourceOptions([]); }, [route.section, route.view, machineId]);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.dataset.theme = theme === "dark" || (theme === "system" && media.matches) ? "dark" : "light";
    localStorage.setItem("axonx-theme", theme); apply(); media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  const content = useMemo(() => {
    if (route.section === "home") return <HomePage language={language} onNavigate={(page) => navigate(page === "submit" ? defaultRoute("task-defs") : page === "tasks" ? { section: "runtime", view: "tasks" } : defaultRoute("home"))} />;
    if (route.section === "runtime") return <RuntimeWorkspace language={language} machine={selectedMachine} remoteIp={remoteIp} view={route.view === "tasks" ? "tasks" : route.view === "environment" ? "environment" : "resources"} taskId={route.resource} onNavigate={(view, resource) => navigate({ section: "runtime", view, resource })} onSubmit={() => navigate({ section: "task-defs", view: "catalog" })} onOptionsChange={setResourceOptions} onConnection={setServiceOnline} />;
    if (route.section === "raw") return <TushareBrowserPage language={language} remoteIp={remoteIp} initialPath={route.resource} onConnection={setServiceOnline} onPathChange={(path) => navigate({ section: "raw", view: "files", resource: path || undefined })} onOptionsChange={setResourceOptions} />;
    if (["etl", "factors", "training", "predict", "backtest"].includes(route.section)) {
      const kind = route.section === "factors" ? "analysis" : route.section;
      return <ResearchPage kind={kind as "analysis" | "backtest" | "etl" | "training" | "predict"} language={language} remoteIp={remoteIp} initialSelectedId={route.resource} onSelected={(resource) => navigate({ section: route.section, view: "runs", resource })} onOptionsChange={setResourceOptions} onConnection={setServiceOnline} onNavigate={(page: PageId, resource?: string) => navigate({ section: page === "factors" ? "factors" : page as SectionId, view: "runs", resource })} />;
    }
    if (route.section === "apis") return <ApiWorkspace language={language} machine={selectedMachine} initialName={route.resource} onSelected={(resource) => navigate({ section: "apis", view: "catalog", resource })} onOptionsChange={setResourceOptions} onConnection={setServiceOnline} />;
    return <SubmitPage language={language} remoteIp={remoteIp} initialName={route.resource} onSelected={(resource) => navigate({ section: "task-defs", view: "catalog", resource })} onOptionsChange={setResourceOptions} onViewTasks={() => navigate({ section: "runtime", view: "tasks" })} onConnection={setServiceOnline} />;
  }, [route, language, selectedMachine, remoteIp, navigate]);

  const machineLabel = selectedMachine?.isLocal ? (language === "zh" ? "本机" : "Local") : selectedMachine?.address;
  const resourceOption = resourceOptions.find((item) => item.value === route.resource);
  const resourceLabel = resourceOption?.label || route.resource;
  const rawFileSelected = route.section === "raw" && resourceOption && resourceOption.detail !== "目录" && resourceOption.detail !== "Folder";
  const finalLabel = route.resource && (rawFileSelected ? (language === "zh" ? "文件预览" : "File preview") : ["etl", "factors", "training", "predict", "backtest"].includes(route.section) ? (language === "zh" ? "数据预览" : "Data preview") : route.section === "apis" ? (language === "zh" ? "接口调用" : "API call") : route.section === "task-defs" ? (language === "zh" ? "参数与提交" : "Configure & submit") : undefined);

  const toggleSidebar = () => setSidebarCollapsed((value) => { localStorage.setItem("axonx-sidebar", value ? "expanded" : "collapsed"); return !value; });

  return <div className={`studio-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`} style={{ "--primary-width": `${sidebarWidth}px` } as CSSProperties}>
    <header className="studio-topbar">
      <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></button>
      <button className="studio-brand" onClick={() => navigate(defaultRoute("home"))}><img src="/axonx-icon.svg" alt="" /><span><strong>AxonX Studio</strong><small><i className={serviceOnline ? "online" : serviceOnline === false ? "offline" : ""} /><b>{serviceOnline ? (language === "zh" ? "在线" : "online") : serviceOnline === false ? (language === "zh" ? "离线" : "offline") : (language === "zh" ? "连接中" : "connecting")}</b></small></span></button>
      <nav className="pathbar" aria-label={language === "zh" ? "当前位置" : "Current path"}>
        <PathPicker label={machineLabel} options={machines.map((item) => ({ value: item.id, label: item.isLocal ? (language === "zh" ? "本机" : "Local") : item.address, detail: item.healthy ? (language === "zh" ? "在线" : "Online") : (language === "zh" ? "离线" : "Offline") }))} onSelect={(id) => { setMachineId(id); window.location.hash = routeHref(id, route); }} />
        <ChevronRight />
        <PathPicker label={sectionLabel} options={sections.map((item) => ({ value: item.id, label: item[language] }))} onSelect={(id) => navigate(defaultRoute(id as SectionId))} />
        {route.section === "runtime" && <><ChevronRight /><PathPicker label={route.view === "tasks" ? (language === "zh" ? "Task 管理" : "Task management") : route.view === "environment" ? (language === "zh" ? "运行环境" : "Environment") : (language === "zh" ? "机器资源" : "Machine resources")} options={[{ value: "resources", label: language === "zh" ? "机器资源" : "Machine resources" }, { value: "tasks", label: language === "zh" ? "Task 管理" : "Task management" }, { value: "environment", label: language === "zh" ? "运行环境" : "Environment" }]} onSelect={(view) => navigate({ section: "runtime", view })} /></>}
        {route.section !== "home" && (route.section !== "runtime" || route.view === "tasks") && <><ChevronRight /><PathPicker label={resourceLabel || (language === "zh" ? "选择资源" : "Select resource")} options={resourceOptions} muted={!route.resource} onSelect={(resource) => navigate({ section: route.section, view: route.view, resource })} /></>}
        {finalLabel && <><ChevronRight /><span className="path-final">{finalLabel}</span></>}
      </nav>
      <div className="studio-actions">
        <button className="topbar-control language-button" onClick={() => setLanguage(language === "zh" ? "en" : "zh")}><Languages /><span>{language === "zh" ? "EN" : "中文"}</span></button>
        <div className="theme-picker"><button className="topbar-control theme-trigger">{theme === "light" ? <Sun /> : theme === "dark" ? <Moon /> : <span className="system-icon">◐</span>}<span>{text[theme]}</span><ChevronDown /></button><div className="theme-menu">{(["system", "light", "dark"] as ThemePreference[]).map((value) => <button key={value} className={theme === value ? "active" : ""} onClick={() => setTheme(value)}>{text[value]}</button>)}</div></div>
        <a className="topbar-control github-link" href="https://github.com/FlowLLM-AI/AxonX" target="_blank" rel="noreferrer" aria-label="GitHub"><GitHubMark /></a>
      </div>
    </header>
    <div className="studio-body">
      <aside className={`primary-rail ${mobileOpen ? "mobile-open" : ""}`}>
        <nav>{sections.map(({ id, icon: Icon, zh, en }) => <button key={id} className={route.section === id ? "active" : ""} onClick={() => navigate(defaultRoute(id))} title={language === "zh" ? zh : en}><Icon /><span>{language === "zh" ? zh : en}</span></button>)}</nav>
        <button className="primary-collapse" onClick={toggleSidebar}>{sidebarCollapsed ? <PanelLeftOpen /> : <><PanelLeftClose /><span>{language === "zh" ? "收起导航" : "Collapse"}</span></>}</button>
      </aside>
      <RailResizer min={70} max={360} className="primary-resizer" onResize={(width) => { if (sidebarCollapsed) setSidebarCollapsed(false); setSidebarWidth(width); }} onResizeEnd={(width) => {
        if (width < 160) {
          setSidebarCollapsed(true);
          localStorage.setItem("axonx-sidebar", "collapsed");
          const saved = Number(localStorage.getItem("axonx-sidebar-width"));
          setSidebarWidth(saved >= 190 && saved <= 360 ? saved : 248);
        } else {
          setSidebarWidth(width);
          localStorage.setItem("axonx-sidebar-width", String(width));
          localStorage.setItem("axonx-sidebar", "expanded");
        }
      }} />
      {mobileOpen && <button className="primary-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation" />}
      <main className="studio-workspace">{content}</main>
    </div>
  </div>;
}

function PathPicker({ label, options, muted, onSelect }: { label: string; options: ContextOption[]; muted?: boolean; onSelect: (value: string) => void }) {
  return <div className="path-picker"><button className={muted ? "muted" : ""}>{label}</button><div className="path-menu">{options.map((option) => <button key={option.value} className={option.label === label ? "active" : ""} onClick={() => onSelect(option.value)}><span>{option.label}</span>{option.detail && <small>{option.detail}</small>}</button>)}</div></div>;
}

function GitHubMark() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.24c-3.23.7-3.91-1.37-3.91-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.26 3.38.96.1-.75.41-1.26.74-1.55-2.58-.29-5.29-1.29-5.29-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.16 1.18a10.96 10.96 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.58.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.72 5.39-5.31 5.68.42.36.79 1.07.79 2.16v3.26c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" /></svg>;
}
