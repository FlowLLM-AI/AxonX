import type { CSSProperties, ReactNode } from "react";
import {
  ChevronDown,
  ChevronRight,
  Languages,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
} from "lucide-react";
import { t } from "../i18n";
import { RailResizer } from "../shared/ui/RailResizer";
import type {
  ContextOption,
  Language,
  MachineNode,
  ThemePreference,
} from "../types";
import { navigationItems, researchSections } from "./navigation";
import { defaultRoute } from "./routes";
import type { AppRoute, SectionId } from "./routes";

interface SidebarState {
  collapsed: boolean;
  width: number;
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
  toggle: () => void;
  resize: (width: number) => void;
  finishResize: (width: number) => void;
}

interface AppShellProps {
  children: ReactNode;
  route: AppRoute;
  language: Language;
  setLanguage: (language: Language) => void;
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  serviceOnline: boolean | null;
  machines: MachineNode[];
  selectedMachine: MachineNode;
  resourceOptions: ContextOption[];
  sidebar: SidebarState;
  navigate: (route: AppRoute, machineId?: string) => void;
}

export function AppShell(props: AppShellProps) {
  const {
    children,
    route,
    language,
    setLanguage,
    theme,
    setTheme,
    serviceOnline,
    machines,
    selectedMachine,
    resourceOptions,
    sidebar,
    navigate,
  } = props;
  const text = t(language);
  const section =
    navigationItems.find((item) => item.id === route.section) ||
    navigationItems[0];
  const machineLabel = selectedMachine.isLocal
    ? language === "zh"
      ? "本机"
      : "Local"
    : selectedMachine.address;
  const resourceOption = resourceOptions.find(
    (item) => item.value === route.resource,
  );
  const resourceLabel = resourceOption?.label || route.resource;
  const rawFileSelected =
    route.section === "raw" &&
    resourceOption &&
    !["目录", "Folder"].includes(resourceOption.detail || "");
  const finalLabel =
    route.resource &&
    (rawFileSelected
      ? language === "zh"
        ? "文件预览"
        : "File preview"
      : researchSections.has(route.section)
        ? language === "zh"
          ? "数据预览"
          : "Data preview"
        : route.section === "apis"
          ? language === "zh"
            ? "接口调用"
            : "API call"
          : route.section === "task-defs"
            ? language === "zh"
              ? "参数与提交"
              : "Configure & submit"
            : undefined);

  return (
    <div
      className={`studio-shell route-${route.section} ${sidebar.collapsed ? "sidebar-collapsed" : ""}`}
      style={{ "--primary-width": `${sidebar.width}px` } as CSSProperties}
    >
      <header className="studio-topbar">
        <button
          className="mobile-menu"
          onClick={() => sidebar.setMobileOpen(true)}
          aria-label="Open navigation"
        >
          <Menu />
        </button>
        <button
          className="studio-brand"
          onClick={() => navigate(defaultRoute("home"))}
        >
          <img src="/axonx-icon.svg" alt="" />
          <span>
            <strong>AxonX Studio</strong>
            <small>
              <i
                className={
                  serviceOnline
                    ? "online"
                    : serviceOnline === false
                      ? "offline"
                      : ""
                }
              />
              <b>
                {serviceOnline
                  ? language === "zh"
                    ? "在线"
                    : "online"
                  : serviceOnline === false
                    ? language === "zh"
                      ? "离线"
                      : "offline"
                    : language === "zh"
                      ? "连接中"
                      : "connecting"}
              </b>
            </small>
          </span>
        </button>
        <nav
          className="pathbar"
          aria-label={language === "zh" ? "当前位置" : "Current path"}
        >
          <PathPicker
            label={machineLabel}
            options={machines.map((machine) => ({
              value: machine.id,
              label: machine.isLocal
                ? language === "zh"
                  ? "本机"
                  : "Local"
                : machine.address,
              detail: machine.healthy
                ? language === "zh"
                  ? "在线"
                  : "Online"
                : language === "zh"
                  ? "离线"
                  : "Offline",
            }))}
            onSelect={(id) => navigate(route, id)}
          />
          <ChevronRight />
          <PathPicker
            label={section[language]}
            options={navigationItems.map((item) => ({
              value: item.id,
              label: item[language],
            }))}
            onSelect={(id) => navigate(defaultRoute(id as SectionId))}
          />
          {route.section === "runtime" && (
            <>
              <ChevronRight />
              <PathPicker
                label={runtimeViewLabel(route.view, language)}
                options={runtimeOptions(language)}
                onSelect={(view) => navigate({ section: "runtime", view })}
              />
            </>
          )}
          {route.section !== "home" &&
            (route.section !== "runtime" || route.view === "tasks") && (
              <>
                <ChevronRight />
                <PathPicker
                  label={
                    resourceLabel ||
                    (language === "zh" ? "选择资源" : "Select resource")
                  }
                  options={resourceOptions}
                  muted={!route.resource}
                  onSelect={(resource) => navigate({ ...route, resource })}
                />
              </>
            )}
          {finalLabel && (
            <>
              <ChevronRight />
              <span className="path-final">{finalLabel}</span>
            </>
          )}
        </nav>
        <div className="studio-actions">
          <button
            className="topbar-control language-button"
            onClick={() => setLanguage(language === "zh" ? "en" : "zh")}
          >
            <Languages />
            <span>{language === "zh" ? "EN" : "中文"}</span>
          </button>
          <div className="theme-picker">
            <button className="topbar-control theme-trigger">
              {theme === "light" ? (
                <Sun />
              ) : theme === "dark" ? (
                <Moon />
              ) : (
                <span className="system-icon">◐</span>
              )}
              <span>{text[theme]}</span>
              <ChevronDown />
            </button>
            <div className="theme-menu">
              {(["system", "light", "dark"] as ThemePreference[]).map(
                (value) => (
                  <button
                    key={value}
                    className={theme === value ? "active" : ""}
                    onClick={() => setTheme(value)}
                  >
                    {text[value]}
                  </button>
                ),
              )}
            </div>
          </div>
          <a
            className="topbar-control github-link"
            href="https://github.com/FlowLLM-AI/AxonX"
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub"
          >
            <GitHubMark />
          </a>
        </div>
      </header>
      <div className="studio-body">
        <aside
          className={`primary-rail ${sidebar.mobileOpen ? "mobile-open" : ""}`}
        >
          <nav>
            {navigationItems.map(({ id, icon: Icon, zh, en }) => (
              <button
                key={id}
                className={route.section === id ? "active" : ""}
                onClick={() => {
                  navigate(defaultRoute(id));
                  sidebar.setMobileOpen(false);
                }}
                title={language === "zh" ? zh : en}
              >
                <Icon />
                <span>{language === "zh" ? zh : en}</span>
              </button>
            ))}
          </nav>
          <button className="primary-collapse" onClick={sidebar.toggle}>
            {sidebar.collapsed ? (
              <PanelLeftOpen />
            ) : (
              <>
                <PanelLeftClose />
                <span>{language === "zh" ? "收起导航" : "Collapse"}</span>
              </>
            )}
          </button>
        </aside>
        <RailResizer
          min={70}
          max={360}
          className="primary-resizer"
          onResize={sidebar.resize}
          onResizeEnd={sidebar.finishResize}
        />
        {sidebar.mobileOpen && (
          <button
            className="primary-scrim"
            onClick={() => sidebar.setMobileOpen(false)}
            aria-label="Close navigation"
          />
        )}
        <main className="studio-workspace">{children}</main>
      </div>
    </div>
  );
}

function runtimeViewLabel(view: string | undefined, language: Language) {
  if (view === "tasks")
    return language === "zh" ? "Task 管理" : "Task management";
  if (view === "environment")
    return language === "zh" ? "运行环境" : "Environment";
  return language === "zh" ? "机器资源" : "Machine resources";
}

function runtimeOptions(language: Language): ContextOption[] {
  return [
    {
      value: "resources",
      label: language === "zh" ? "机器资源" : "Machine resources",
    },
    {
      value: "tasks",
      label: language === "zh" ? "Task 管理" : "Task management",
    },
    {
      value: "environment",
      label: language === "zh" ? "运行环境" : "Environment",
    },
  ];
}

function PathPicker({
  label,
  options,
  muted,
  onSelect,
}: {
  label: string;
  options: ContextOption[];
  muted?: boolean;
  onSelect: (value: string) => void;
}) {
  return (
    <div className="path-picker">
      <button className={muted ? "muted" : ""}>{label}</button>
      <div className="path-menu">
        {options.map((option) => (
          <button
            key={option.value}
            className={option.label === label ? "active" : ""}
            onClick={() => onSelect(option.value)}
          >
            <span>{option.label}</span>
            {option.detail && <small>{option.detail}</small>}
          </button>
        ))}
      </div>
    </div>
  );
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 .7a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2.24c-3.23.7-3.91-1.37-3.91-1.37-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.26 3.38.96.1-.75.41-1.26.74-1.55-2.58-.29-5.29-1.29-5.29-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.16 1.18a10.96 10.96 0 0 1 5.76 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.58.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.72 5.39-5.31 5.68.42.36.79 1.07.79 2.16v3.26c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z"
      />
    </svg>
  );
}
