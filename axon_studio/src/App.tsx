import { useEffect, useMemo, useState } from "react";
import {
  Activity, BarChart3, Box, BrainCircuit, ChevronDown, Cpu, Database,
  Languages, Moon, Play, Send, Sun, Workflow,
} from "lucide-react";
import { API_URL } from "./api";
import { t } from "./i18n";
import { MachinesPage } from "./MachinesPage";
import { SubmitPage } from "./SubmitPage";
import { TasksPage } from "./TasksPage";
import type { Language, PageId, ThemePreference } from "./types";
import { useAxonXWebMcp } from "./webmcp";

const pages: Array<{ id: PageId; icon: typeof Cpu }> = [
  { id: "machines", icon: Cpu }, { id: "tasks", icon: Activity }, { id: "submit", icon: Send },
  { id: "rawData", icon: Database }, { id: "factors", icon: Workflow }, { id: "training", icon: BrainCircuit },
  { id: "prediction", icon: Play }, { id: "backtest", icon: BarChart3 },
];

const initialPage = (): PageId => {
  const value = window.location.hash.slice(1) as PageId;
  return pages.some((page) => page.id === value) ? value : "tasks";
};

export default function App() {
  useAxonXWebMcp();
  const [language, setLanguage] = useState<Language>(() => (localStorage.getItem("axonx-language") === "en" ? "en" : "zh"));
  const [theme, setTheme] = useState<ThemePreference>(() => {
    const saved = localStorage.getItem("axonx-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });
  const [page, setPageState] = useState<PageId>(initialPage);
  const [serviceOnline, setServiceOnline] = useState<boolean | null>(null);
  const text = t(language);

  const setPage = (next: PageId) => {
    window.location.hash = next;
    setPageState(next);
  };

  useEffect(() => {
    const onHash = () => setPageState(initialPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    localStorage.setItem("axonx-language", language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && media.matches);
      document.documentElement.dataset.theme = dark ? "dark" : "light";
    };
    localStorage.setItem("axonx-theme", theme);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    let alive = true;
    const check = () => fetch(`${API_URL}/health`).then((response) => response.ok ? response.json() : null)
      .then((data) => alive && setServiceOnline(data?.running === true)).catch(() => alive && setServiceOnline(false));
    check();
    const timer = window.setInterval(check, 15_000);
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const content = useMemo(() => {
    if (page === "machines") return <MachinesPage language={language} onConnection={setServiceOnline} />;
    if (page === "tasks") return <TasksPage language={language} onSubmit={() => setPage("submit")} onConnection={setServiceOnline} />;
    if (page === "submit") return <SubmitPage language={language} onViewTasks={() => setPage("tasks")} onConnection={setServiceOnline} />;
    return <Placeholder page={page} language={language} />;
  }, [page, language]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <button className="brand" onClick={() => setPage("tasks")} aria-label="AxonX Studio">
          <span className="brand-mark"><i /><i /><i /><Box size={18} /></span>
          <span><strong>Axon<span>X</span></strong><small>{text.studio}</small></span>
        </button>
        <nav className="main-tabs" aria-label="Main navigation">
          {pages.map(({ id, icon: Icon }) => (
            <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
              <Icon size={17} strokeWidth={1.8} /><span>{text.pages[id]}</span>
            </button>
          ))}
        </nav>
        <div className="header-actions">
          <div className={`service-pill ${serviceOnline === true ? "online" : serviceOnline === false ? "offline" : ""}`}>
            <i /> <span>{serviceOnline === false ? text.serviceOffline : text.serviceOnline}</span>
          </div>
          <button className="icon-button language-button" onClick={() => setLanguage(language === "zh" ? "en" : "zh")} title="Language">
            <Languages size={17} /><span>{language === "zh" ? "EN" : "中"}</span>
          </button>
          <div className="theme-picker">
            <button className="icon-button" aria-label={text.appearance}>
              {theme === "light" ? <Sun size={17} /> : theme === "dark" ? <Moon size={17} /> : <span className="system-icon">◐</span>}
              <ChevronDown size={13} />
            </button>
            <div className="theme-menu">
              {(["system", "light", "dark"] as ThemePreference[]).map((value) => (
                <button key={value} className={theme === value ? "active" : ""} onClick={() => setTheme(value)}>{text[value]}</button>
              ))}
            </div>
          </div>
        </div>
      </header>
      <main>{content}</main>
    </div>
  );
}

function Placeholder({ page, language }: { page: PageId; language: Language }) {
  const text = t(language);
  const pageInfo = pages.find((item) => item.id === page)!;
  const Icon = pageInfo.icon;
  return <section className="placeholder-page"><div className="placeholder-orbit"><Icon size={34} /></div><p>{text.pages[page]}</p><h1>{text.comingSoon}</h1><span>{text.comingHint}</span></section>;
}
