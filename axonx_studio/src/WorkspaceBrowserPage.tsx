import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, ChevronDown, ChevronRight, Copy, Database, Eye, File, FileJson,
  FileCode2, FileSpreadsheet, FileText, Folder, FolderOpen, HardDrive,
  LoaderCircle, RefreshCw, Trash2, X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { deleteWorkspaceEntry, listWorkspaceEntries, previewWorkspaceFile } from "./api";
import type { Language, WorkspaceDirectory, WorkspaceEntry, WorkspacePreview } from "./types";

const labels = {
  zh: {
    title: "工作区", lead: "浏览当前机器 workspace_dir 中的数据与任务产物。", tree: "目录",
    root: "workspace_dir", refresh: "刷新", empty: "目录为空", select: "选择左侧文件查看内容",
    unsupported: "暂不支持预览此文件", parquet: "Parquet 文件", parquetHint: "当前版本仅展示文件信息，不读取数据内容。",
    loadFailed: "工作区读取失败", previewFailed: "文件预览失败", truncated: "内容过大，仅展示前 512 KiB",
    invalidJson: "JSON 格式有误", invalidYaml: "YAML 格式有误", frontmatter: "Frontmatter", rows: "行", previous: "上一页", next: "下一页",
    entriesTruncated: "目录项目过多，仅展示前 5,000 项", modified: "修改时间", size: "文件大小",
    previewAction: "预览", expand: "展开目录", collapse: "收起目录", refreshDirectory: "刷新目录", copyPath: "复制相对路径",
    deleteAction: "删除", deleteTitle: "确认删除？", deleteFileHint: "文件将被永久删除，此操作无法撤销。", deleteFolderHint: "目录及其中的全部内容将被永久删除，此操作无法撤销。", cancel: "取消", deleting: "删除中…", deleteFailed: "删除失败",
  },
  en: {
    title: "Workspace", lead: "Browse data and task artifacts in this machine's workspace_dir.", tree: "FILES",
    root: "workspace_dir", refresh: "Refresh", empty: "This directory is empty", select: "Select a file to preview it",
    unsupported: "Preview is not supported for this file", parquet: "Parquet file", parquetHint: "This version shows file information without reading its data.",
    loadFailed: "Unable to read workspace", previewFailed: "Unable to preview file", truncated: "Large file: showing the first 512 KiB",
    invalidJson: "Invalid JSON", invalidYaml: "Invalid YAML", frontmatter: "Frontmatter", rows: "rows", previous: "Previous", next: "Next",
    entriesTruncated: "Too many entries: showing the first 5,000", modified: "Modified", size: "File size",
    previewAction: "Preview", expand: "Expand folder", collapse: "Collapse folder", refreshDirectory: "Refresh folder", copyPath: "Copy relative path",
    deleteAction: "Delete", deleteTitle: "Delete this item?", deleteFileHint: "The file will be permanently deleted. This cannot be undone.", deleteFolderHint: "The folder and all of its contents will be permanently deleted. This cannot be undone.", cancel: "Cancel", deleting: "Deleting…", deleteFailed: "Delete failed",
  },
} as const;

const formatBytes = (size: number | null) => {
  if (size === null) return "—";
  if (size < 1024) return `${size} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = size / 1024; let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value < 10 ? value.toFixed(1) : value.toFixed(0)} ${units[index]}`;
};

const entryIcon = (entry: WorkspaceEntry) => {
  if (entry.kind === "directory") return Folder;
  if (entry.preview_kind === "markdown") return FileText;
  if (entry.preview_kind === "json" || entry.preview_kind === "yaml") return FileJson;
  if (entry.preview_kind === "csv") return FileSpreadsheet;
  if (entry.preview_kind === "parquet") return Database;
  if (entry.preview_kind === "text") return FileCode2;
  return File;
};

type WorkspaceTabSession = { machineKey: string; tabs: WorkspaceEntry[]; activePath: string };
const MAX_OPEN_TABS = 10;

const readTabSession = (machineKey: string): WorkspaceTabSession => {
  try {
    const tabs = JSON.parse(localStorage.getItem(`axonx-workspace-tabs:${machineKey}`) || "[]") as WorkspaceEntry[];
    const files = Array.isArray(tabs) ? tabs.filter((entry) => entry?.kind === "file" && typeof entry.path === "string").slice(-MAX_OPEN_TABS) : [];
    const storedActive = localStorage.getItem(`axonx-workspace-active-tab:${machineKey}`) || "";
    return { machineKey, tabs: files, activePath: files.some((entry) => entry.path === storedActive) ? storedActive : files[0]?.path || "" };
  } catch {
    return { machineKey, tabs: [], activePath: "" };
  }
};

export function WorkspaceBrowserPage({ language, remoteIp, onConnection }: {
  language: Language; remoteIp?: string; onConnection: (online: boolean) => void;
}) {
  const text = labels[language];
  const machineKey = remoteIp || "local";
  const [directories, setDirectories] = useState<Record<string, WorkspaceDirectory>>({});
  const [expanded, setExpanded] = useState(() => new Set<string>([""]));
  const [loadingDirs, setLoadingDirs] = useState(() => new Set<string>());
  const [tabSession, setTabSession] = useState<WorkspaceTabSession>(() => readTabSession(machineKey));
  const [preview, setPreview] = useState<WorkspacePreview | null>(null);
  const [error, setError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewRequest = useRef(0);
  const [contextMenu, setContextMenu] = useState<{ entry: WorkspaceEntry; x: number; y: number } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceEntry | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [visibleTabCount, setVisibleTabCount] = useState(MAX_OPEN_TABS);
  const [tabOverflowOpen, setTabOverflowOpen] = useState(false);
  const tabBar = useRef<HTMLDivElement>(null);
  const selected = tabSession.tabs.find((entry) => entry.path === tabSession.activePath) || null;

  const loadDirectory = useCallback(async (path: string, signal?: AbortSignal) => {
    setLoadingDirs((current) => new Set(current).add(path));
    try {
      const result = await listWorkspaceEntries(path, remoteIp, signal);
      setDirectories((current) => ({ ...current, [path]: result }));
      setError(""); onConnection(true);
    } catch (reason) {
      if ((reason as { name?: string })?.name !== "AbortError") {
        setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
      }
    } finally {
      setLoadingDirs((current) => { const next = new Set(current); next.delete(path); return next; });
    }
  }, [remoteIp, onConnection]);

  const loadPreview = useCallback(async (entry: WorkspaceEntry, offset = 0) => {
    const requestId = ++previewRequest.current;
    setTabSession((current) => {
      const base = current.machineKey === machineKey ? current : readTabSession(machineKey);
      const tabs = base.tabs.some((tab) => tab.path === entry.path) ? base.tabs : [...base.tabs, entry].slice(-MAX_OPEN_TABS);
      return { machineKey, tabs, activePath: entry.path };
    });
    setPreview(null); setPreviewError(""); setPreviewLoading(true);
    try {
      const result = await previewWorkspaceFile(entry.path, offset, 200, remoteIp);
      if (requestId === previewRequest.current) { setPreview(result); onConnection(true); }
    } catch (reason) {
      if (requestId === previewRequest.current) { setPreviewError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    } finally { if (requestId === previewRequest.current) setPreviewLoading(false); }
  }, [remoteIp, onConnection, machineKey]);

  useEffect(() => {
    const controller = new AbortController();
    const restored = readTabSession(machineKey);
    previewRequest.current += 1; setTabSession(restored); setTabOverflowOpen(false); setDirectories({}); setExpanded(new Set([""])); setPreview(null); setPreviewLoading(false); setError("");
    void loadDirectory("", controller.signal);
    const restoredEntry = restored.tabs.find((entry) => entry.path === restored.activePath);
    if (restoredEntry) void loadPreview(restoredEntry);
    return () => { controller.abort(); previewRequest.current += 1; };
  }, [machineKey, loadDirectory, loadPreview]);
  useEffect(() => {
    if (tabSession.machineKey !== machineKey) return;
    localStorage.setItem(`axonx-workspace-tabs:${machineKey}`, JSON.stringify(tabSession.tabs));
    if (tabSession.activePath) localStorage.setItem(`axonx-workspace-active-tab:${machineKey}`, tabSession.activePath);
    else localStorage.removeItem(`axonx-workspace-active-tab:${machineKey}`);
  }, [machineKey, tabSession]);
  useEffect(() => {
    const element = tabBar.current;
    if (!element) return;
    const update = () => setVisibleTabCount(Math.max(1, Math.min(MAX_OPEN_TABS, Math.floor((element.clientWidth - 54) / 170))));
    update();
    const observer = new ResizeObserver(update); observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!tabOverflowOpen) return;
    const close = () => setTabOverflowOpen(false);
    window.addEventListener("click", close); window.addEventListener("blur", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); };
  }, [tabOverflowOpen]);
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close); window.removeEventListener("blur", close);
      window.removeEventListener("keydown", onKeyDown); window.removeEventListener("scroll", close, true);
    };
  }, [contextMenu]);

  const toggleDirectory = (path: string) => {
    const opening = !expanded.has(path);
    setExpanded((current) => { const next = new Set(current); if (opening) next.add(path); else next.delete(path); return next; });
    if (opening && !directories[path]) void loadDirectory(path);
  };

  const refresh = () => {
    setDirectories({}); setExpanded(new Set([""])); setError("");
    void loadDirectory("");
    if (selected) void loadPreview(selected);
  };

  const closeTab = (path: string) => {
    const index = tabSession.tabs.findIndex((entry) => entry.path === path);
    const remaining = tabSession.tabs.filter((entry) => entry.path !== path);
    if (tabSession.activePath !== path) {
      setTabSession({ machineKey, tabs: remaining, activePath: tabSession.activePath }); return;
    }
    const next = remaining[Math.min(Math.max(index, 0), remaining.length - 1)] || null;
    setTabSession({ machineKey, tabs: remaining, activePath: next?.path || "" });
    previewRequest.current += 1; setPreview(null); setPreviewError(""); setPreviewLoading(false);
    if (next) void loadPreview(next);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteError("");
    try {
      await deleteWorkspaceEntry(deleteTarget.path, remoteIp);
      const deletedPath = deleteTarget.path;
      const separator = deletedPath.lastIndexOf("/");
      const parentPath = separator < 0 ? "" : deletedPath.slice(0, separator);
      setDirectories((current) => Object.fromEntries(Object.entries(current).filter(([path]) => path !== deletedPath && !path.startsWith(`${deletedPath}/`))));
      setExpanded((current) => { const next = new Set(current); next.delete(deletedPath); return next; });
      const remainingTabs = tabSession.tabs.filter((entry) => entry.path !== deletedPath && !entry.path.startsWith(`${deletedPath}/`));
      const activeWasDeleted = tabSession.activePath === deletedPath || tabSession.activePath.startsWith(`${deletedPath}/`);
      const next = activeWasDeleted ? remainingTabs[0] || null : selected;
      setTabSession({ machineKey, tabs: remainingTabs, activePath: next?.path || "" });
      if (activeWasDeleted) { previewRequest.current += 1; setPreview(null); setPreviewError(""); setPreviewLoading(false); if (next) void loadPreview(next); }
      setDeleteTarget(null); await loadDirectory(parentPath); onConnection(true);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
    } finally { setDeleting(false); }
  };

  const renderDirectory = (path: string, depth: number): React.ReactNode => {
    const directory = directories[path];
    if (!directory) return loadingDirs.has(path) ? <div className="workspace-tree-loading" style={{ paddingLeft: 20 + depth * 17 }}><LoaderCircle className="spin" /></div> : null;
    return <>
      {directory.entries.map((entry) => {
        const Icon = entryIcon(entry); const isDirectory = entry.kind === "directory"; const isOpen = expanded.has(entry.path);
        return <div key={entry.path}>
          <button
            className={`workspace-tree-row ${selected?.path === entry.path || contextMenu?.entry.path === entry.path ? "active" : ""} ${entry.kind === "symlink" ? "disabled" : ""}`}
            style={{ paddingLeft: 12 + depth * 17 }}
            onClick={() => isDirectory ? toggleDirectory(entry.path) : entry.kind === "file" && void loadPreview(entry)}
            onContextMenu={(event) => {
              event.preventDefault();
              setContextMenu({ entry, x: Math.max(6, Math.min(event.clientX, window.innerWidth - 224)), y: Math.max(6, Math.min(event.clientY, window.innerHeight - 190)) });
            }}
            disabled={entry.kind === "symlink"}
            title={entry.path}
          >
            <span className="tree-chevron">{isDirectory ? (isOpen ? <ChevronDown /> : <ChevronRight />) : null}</span>
            <Icon /><span>{entry.name}</span>{entry.kind === "file" && <small>{formatBytes(entry.size)}</small>}
          </button>
          {isDirectory && isOpen && renderDirectory(entry.path, depth + 1)}
        </div>;
      })}
      {directory.entries.length === 0 && <div className="workspace-tree-empty" style={{ paddingLeft: 20 + depth * 17 }}>{text.empty}</div>}
      {directory.truncated && <div className="workspace-tree-warning">{text.entriesTruncated}</div>}
    </>;
  };

  const visiblePaths = tabSession.tabs.slice(-visibleTabCount).map((entry) => entry.path);
  if (tabSession.activePath && !visiblePaths.includes(tabSession.activePath)) visiblePaths[0] = tabSession.activePath;
  const visibleTabs = tabSession.tabs.filter((entry) => visiblePaths.includes(entry.path));
  const overflowTabs = tabSession.tabs.filter((entry) => !visiblePaths.includes(entry.path));
  const renderTab = (entry: WorkspaceEntry, overflow = false) => {
    const Icon = entryIcon(entry); const active = entry.path === tabSession.activePath;
    return <button key={entry.path} className={active ? "active" : ""} role="tab" aria-selected={active} title={entry.path} onClick={() => { void loadPreview(entry); setTabOverflowOpen(false); }} onAuxClick={(event) => { if (event.button === 1) closeTab(entry.path); }} onContextMenu={(event) => { event.preventDefault(); setTabOverflowOpen(false); setContextMenu({ entry, x: Math.max(6, Math.min(event.clientX, window.innerWidth - 224)), y: Math.max(6, Math.min(event.clientY, window.innerHeight - 190)) }); }}><Icon /><span>{entry.name}{overflow && <small>{entry.path}</small>}</span><i role="button" tabIndex={0} aria-label={`${text.cancel} ${entry.name}`} onClick={(event) => { event.stopPropagation(); closeTab(entry.path); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); closeTab(entry.path); } }}><X /></i></button>;
  };

  return <section className="workspace-page workspace-browser-page">
    <div className="page-heading"><div><p className="eyebrow">DATA / WORKSPACE</p><h1>{text.title}</h1><span>{text.lead}</span></div><button className="secondary-button" onClick={refresh}><RefreshCw className={loadingDirs.size ? "spin" : ""} />{text.refresh}</button></div>
    {error && <div className="error-banner"><AlertTriangle /><div><strong>{text.loadFailed}</strong><span>{error}</span></div><button onClick={refresh}>{text.refresh}</button></div>}
    <div className="workspace-browser">
      <aside className="workspace-tree-panel">
        <header><div><HardDrive /><span><strong>{text.root}</strong><small>{text.tree}</small></span></div></header>
        <div className="workspace-tree-scroll">
          <button className="workspace-root-row" onClick={() => toggleDirectory("")}><span>{expanded.has("") ? <ChevronDown /> : <ChevronRight />}</span>{expanded.has("") ? <FolderOpen /> : <Folder />}<strong>{text.root}</strong></button>
          {expanded.has("") && renderDirectory("", 0)}
        </div>
      </aside>
      <div className="workspace-preview-panel">
        <div className="workspace-tabs" ref={tabBar} role="tablist" aria-label={text.title}>
          <div className="workspace-visible-tabs">{visibleTabs.map((entry) => renderTab(entry))}</div>
          {overflowTabs.length > 0 && <div className="workspace-tab-overflow" onClick={(event) => event.stopPropagation()}><button className={tabOverflowOpen ? "active" : ""} aria-label={`${overflowTabs.length}`} aria-expanded={tabOverflowOpen} onClick={() => setTabOverflowOpen((open) => !open)}><span>+{overflowTabs.length}</span><ChevronDown /></button>{tabOverflowOpen && <div className="workspace-tab-overflow-menu">{overflowTabs.map((entry) => renderTab(entry, true))}</div>}</div>}
        </div>
        {!selected ? <div className="workspace-preview-empty"><FileCode2 /><strong>{text.select}</strong><span>TXT · MD · JSON · YAML · CSV · PARQUET</span></div> : <>
          <header className="workspace-file-header"><div>{(() => { const Icon = entryIcon(selected); return <Icon />; })()}<span><strong>{selected.name}</strong><small>{selected.path}</small></span></div><div><span>{text.size}<strong>{formatBytes(selected.size)}</strong></span><span>{text.modified}<strong>{new Date(selected.modified_at * 1000).toLocaleString(language === "zh" ? "zh-CN" : "en")}</strong></span></div></header>
          {previewLoading ? <div className="workspace-preview-loading"><LoaderCircle className="spin" /></div> : previewError ? <div className="workspace-preview-message error"><AlertTriangle /><strong>{text.previewFailed}</strong><span>{previewError}</span></div> : preview && <PreviewContent preview={preview} text={text} onPage={(offset) => selected && void loadPreview(selected, offset)} />}
        </>}
      </div>
    </div>
    {contextMenu && <div className="workspace-context-menu" role="menu" style={{ left: contextMenu.x, top: contextMenu.y }} onClick={(event) => event.stopPropagation()}>
      <header><span>{contextMenu.entry.name}</span><small>{contextMenu.entry.preview_kind || contextMenu.entry.kind}</small></header>
      {contextMenu.entry.kind === "file" && contextMenu.entry.supported && <button role="menuitem" onClick={() => { void loadPreview(contextMenu.entry); setContextMenu(null); }}><Eye />{text.previewAction}</button>}
      {contextMenu.entry.kind === "directory" && <button role="menuitem" onClick={() => { toggleDirectory(contextMenu.entry.path); setContextMenu(null); }}>{expanded.has(contextMenu.entry.path) ? <ChevronDown /> : <ChevronRight />}{expanded.has(contextMenu.entry.path) ? text.collapse : text.expand}</button>}
      {contextMenu.entry.kind === "directory" && <button role="menuitem" onClick={() => { setExpanded((current) => new Set(current).add(contextMenu.entry.path)); void loadDirectory(contextMenu.entry.path); setContextMenu(null); }}><RefreshCw />{text.refreshDirectory}</button>}
      <button role="menuitem" onClick={() => { void navigator.clipboard.writeText(contextMenu.entry.path); setContextMenu(null); }}><Copy />{text.copyPath}</button>
      {contextMenu.entry.kind !== "symlink" && <button className="danger" role="menuitem" onClick={() => { setDeleteTarget(contextMenu.entry); setDeleteError(""); setContextMenu(null); }}><Trash2 />{text.deleteAction}</button>}
    </div>}
    {deleteTarget && <div className="modal-backdrop" role="presentation" onClick={() => !deleting && setDeleteTarget(null)}>
      <div className="confirm-modal workspace-delete-modal" role="alertdialog" aria-modal="true" aria-labelledby="workspace-delete-title" onClick={(event) => event.stopPropagation()}>
        <button className="close-button" aria-label={text.cancel} disabled={deleting} onClick={() => setDeleteTarget(null)}><X /></button>
        <div className="danger-icon"><Trash2 /></div><h2 id="workspace-delete-title">{text.deleteTitle}</h2><code>{deleteTarget.path}</code>
        <p>{deleteTarget.kind === "directory" ? text.deleteFolderHint : text.deleteFileHint}</p>
        {deleteError && <div className="inline-error"><strong>{text.deleteFailed}</strong><span>{deleteError}</span></div>}
        <div><button className="secondary-button" disabled={deleting} onClick={() => setDeleteTarget(null)}>{text.cancel}</button><button className="danger-button" disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? <LoaderCircle className="spin" /> : <Trash2 />}{deleting ? text.deleting : text.deleteAction}</button></div>
      </div>
    </div>}
  </section>;
}

function PreviewContent({ preview, text, onPage }: { preview: WorkspacePreview; text: typeof labels.zh | typeof labels.en; onPage: (offset: number) => void }) {
  if (preview.kind === "parquet") return <div className="workspace-preview-message parquet"><Database /><strong>{text.parquet}</strong><span>{text.parquetHint}</span><b>{formatBytes(preview.size)}</b></div>;
  if (preview.kind === "unsupported") return <div className="workspace-preview-message"><File /><strong>{text.unsupported}</strong></div>;
  if (preview.kind === "csv") {
    const offset = preview.offset || 0; const limit = preview.limit || 200;
    return <div className="workspace-csv"><div className="workspace-csv-scroll"><table><thead><tr><th>#</th>{(preview.columns || []).map((column, index) => <th key={`${column}-${index}`}>{column || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{(preview.rows || []).map((row, rowIndex) => <tr key={rowIndex}><td>{offset + rowIndex + 1}</td>{(preview.columns || []).map((_, cellIndex) => <td key={cellIndex}>{row[cellIndex] ?? ""}</td>)}</tr>)}</tbody></table></div><footer><span>{offset + 1}–{offset + (preview.rows?.length || 0)} {text.rows}</span><div><button disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - limit))}>{text.previous}</button><button disabled={!preview.has_more} onClick={() => onPage(offset + limit)}>{text.next}</button></div></footer></div>;
  }
  return <div className="workspace-document">
    {preview.truncated && <div className="workspace-notice"><AlertTriangle />{text.truncated}</div>}
    {preview.kind === "json" && preview.parse_error && <div className="workspace-notice error"><AlertTriangle /><strong>{text.invalidJson}</strong><span>{preview.parse_error}</span></div>}
    {preview.kind === "yaml" && preview.parse_error && <div className="workspace-notice error"><AlertTriangle /><strong>{text.invalidYaml}</strong><span>{preview.parse_error}</span></div>}
    {preview.kind === "markdown" && preview.frontmatter !== null && preview.frontmatter !== undefined && <section className="workspace-frontmatter"><header>{text.frontmatter}</header><pre>{JSON.stringify(preview.frontmatter, null, 2)}</pre></section>}
    {preview.kind === "markdown" && preview.frontmatter_error && <div className="workspace-notice error"><AlertTriangle />{preview.frontmatter_error}</div>}
    {preview.kind === "markdown" ? <article className="workspace-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span className="markdown-image-placeholder">[{alt || "image"}]</span>, a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a> }}>{preview.content || ""}</ReactMarkdown></article> : <pre className="workspace-code">{preview.content || ""}</pre>}
  </div>;
}
