import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, ChevronRight, Copy, Database, Eye, File, FileCode2,
  FileJson, FileSpreadsheet, FileText, Folder, HardDrive, LoaderCircle,
  RefreshCw, Trash2, X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { deleteWorkspaceEntry, listWorkspaceEntries, previewWorkspaceFile } from "./api";
import type { Language, WorkspaceDirectory, WorkspaceEntry, WorkspacePreview } from "./types";

const labels = {
  zh: {
    title: "工作区", lead: "按真实目录逐层浏览当前机器的数据与任务产物。", directory: "目录",
    root: "workspace_dir", refresh: "刷新", empty: "目录为空", select: "选择文件查看内容",
    unsupported: "暂不支持预览此文件", parquet: "Parquet 数据预览", sample: "前 5 行",
    rowCount: "总行数", rowGroups: "Row Groups", fields: "字段数", schema: "字段结构",
    loadFailed: "工作区读取失败", previewFailed: "文件预览失败", truncated: "内容过大，仅展示前 512 KiB",
    invalidJson: "JSON 格式有误", invalidYaml: "YAML 格式有误", frontmatter: "Frontmatter",
    rows: "行", previous: "上一页", next: "下一页", entriesTruncated: "目录项目过多，仅展示前 5,000 项",
    modified: "修改时间", size: "文件大小", previewAction: "预览", open: "打开", copyPath: "复制相对路径",
    deleteAction: "删除", deleteTitle: "确认删除？", deleteFileHint: "文件将被永久删除，此操作无法撤销。",
    deleteFolderHint: "目录及其中的全部内容将被永久删除，此操作无法撤销。", cancel: "取消",
    deleting: "删除中…", deleteFailed: "删除失败",
  },
  en: {
    title: "Workspace", lead: "Browse data and task artifacts through their real directory structure.", directory: "DIRECTORY",
    root: "workspace_dir", refresh: "Refresh", empty: "This directory is empty", select: "Select a file to preview it",
    unsupported: "Preview is not supported for this file", parquet: "Parquet data preview", sample: "First 5 rows",
    rowCount: "Rows", rowGroups: "Row groups", fields: "Fields", schema: "Schema",
    loadFailed: "Unable to read workspace", previewFailed: "Unable to preview file", truncated: "Large file: showing the first 512 KiB",
    invalidJson: "Invalid JSON", invalidYaml: "Invalid YAML", frontmatter: "Frontmatter",
    rows: "rows", previous: "Previous", next: "Next", entriesTruncated: "Too many entries: showing the first 5,000",
    modified: "Modified", size: "File size", previewAction: "Preview", open: "Open", copyPath: "Copy relative path",
    deleteAction: "Delete", deleteTitle: "Delete this item?", deleteFileHint: "The file will be permanently deleted. This cannot be undone.",
    deleteFolderHint: "The folder and all of its contents will be permanently deleted. This cannot be undone.", cancel: "Cancel",
    deleting: "Deleting…", deleteFailed: "Delete failed",
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

export function WorkspaceBrowserPage({ language, remoteIp, onConnection }: {
  language: Language; remoteIp?: string; onConnection: (online: boolean) => void;
}) {
  const text = labels[language];
  const [columnPaths, setColumnPaths] = useState<string[]>([""]);
  const [directories, setDirectories] = useState<Record<string, WorkspaceDirectory>>({});
  const [loadingDirs, setLoadingDirs] = useState(() => new Set<string>());
  const [activePath, setActivePath] = useState("");
  const [selected, setSelected] = useState<WorkspaceEntry | null>(null);
  const [preview, setPreview] = useState<WorkspacePreview | null>(null);
  const [error, setError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewRequest = useRef(0);
  const columnsViewport = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<{ entry: WorkspaceEntry; column: number; x: number; y: number } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceEntry | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

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
    setActivePath(entry.path); setSelected(entry); setPreview(null); setPreviewError(""); setPreviewLoading(true);
    try {
      const result = await previewWorkspaceFile(entry.path, offset, 200, remoteIp);
      if (requestId === previewRequest.current) { setPreview(result); onConnection(true); }
    } catch (reason) {
      if (requestId === previewRequest.current) { setPreviewError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    } finally { if (requestId === previewRequest.current) setPreviewLoading(false); }
  }, [remoteIp, onConnection]);

  const openDirectory = useCallback((entry: WorkspaceEntry, column: number) => {
    previewRequest.current += 1; setActivePath(entry.path); setSelected(null); setPreview(null); setPreviewError(""); setPreviewLoading(false);
    setColumnPaths((current) => [...current.slice(0, column + 1), entry.path]);
    if (!directories[entry.path]) void loadDirectory(entry.path);
  }, [directories, loadDirectory]);

  const selectFile = useCallback((entry: WorkspaceEntry, column: number) => {
    setColumnPaths((current) => current.slice(0, column + 1));
    void loadPreview(entry);
  }, [loadPreview]);

  useEffect(() => {
    const controller = new AbortController();
    previewRequest.current += 1; setColumnPaths([""]); setDirectories({}); setActivePath(""); setSelected(null); setPreview(null); setError("");
    void loadDirectory("", controller.signal);
    return () => { controller.abort(); previewRequest.current += 1; };
  }, [remoteIp, loadDirectory]);

  useEffect(() => {
    const viewport = columnsViewport.current;
    if (!viewport) return;
    requestAnimationFrame(() => viewport.scrollTo({ left: viewport.scrollWidth, behavior: "smooth" }));
  }, [columnPaths.length]);

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("click", close); window.addEventListener("blur", close); window.addEventListener("keydown", onKeyDown); window.addEventListener("scroll", close, true);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); window.removeEventListener("keydown", onKeyDown); window.removeEventListener("scroll", close, true); };
  }, [contextMenu]);

  const refresh = () => {
    setDirectories({}); setColumnPaths([""]); setActivePath(""); setSelected(null); setPreview(null); setPreviewError(""); setError("");
    previewRequest.current += 1; void loadDirectory("");
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true); setDeleteError("");
    try {
      await deleteWorkspaceEntry(deleteTarget.path, remoteIp);
      const deletedPath = deleteTarget.path;
      const slash = deletedPath.lastIndexOf("/"); const parentPath = slash < 0 ? "" : deletedPath.slice(0, slash);
      setDirectories((current) => Object.fromEntries(Object.entries(current).filter(([path]) => path !== deletedPath && !path.startsWith(`${deletedPath}/`))));
      setColumnPaths((current) => current.filter((path) => path !== deletedPath && !path.startsWith(`${deletedPath}/`)));
      if (activePath === deletedPath || activePath.startsWith(`${deletedPath}/`)) {
        previewRequest.current += 1; setActivePath(parentPath); setSelected(null); setPreview(null); setPreviewError("");
      }
      setDeleteTarget(null); await loadDirectory(parentPath); onConnection(true);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : String(reason)); onConnection(false);
    } finally { setDeleting(false); }
  };

  const renderColumn = (path: string, column: number) => {
    const directory = directories[path];
    const title = path ? path.split("/").at(-1) : text.root;
    const entries = [...(directory?.entries || [])].sort((left, right) => {
      const leftDirectory = left.kind === "directory" ? 1 : 0;
      const rightDirectory = right.kind === "directory" ? 1 : 0;
      return leftDirectory - rightDirectory;
    });
    return <section className="workspace-column" key={path} aria-label={title}>
      <header><Folder /><span><strong>{title}</strong><small>{path || text.directory}</small></span></header>
      <div>
        {!directory && loadingDirs.has(path) && <div className="workspace-column-loading"><LoaderCircle className="spin" /></div>}
        {entries.map((entry) => {
          const Icon = entryIcon(entry); const isDirectory = entry.kind === "directory";
          const isActive = activePath === entry.path || columnPaths[column + 1] === entry.path;
          return <button
            key={entry.path}
            className={`${isActive ? "active" : ""} ${entry.kind === "symlink" ? "disabled" : ""}`}
            onClick={() => isDirectory ? openDirectory(entry, column) : entry.kind === "file" && selectFile(entry, column)}
            onContextMenu={(event) => { event.preventDefault(); setContextMenu({ entry, column, x: Math.max(6, Math.min(event.clientX, window.innerWidth - 224)), y: Math.max(6, Math.min(event.clientY, window.innerHeight - 190)) }); }}
            disabled={entry.kind === "symlink"}
            title={entry.path}
          >
            <Icon /><span>{entry.name}</span>{entry.kind === "file" && <small>{formatBytes(entry.size)}</small>}{isDirectory && <ChevronRight />}
          </button>;
        })}
        {directory?.entries.length === 0 && <div className="workspace-column-empty">{text.empty}</div>}
        {directory?.truncated && <div className="workspace-column-warning">{text.entriesTruncated}</div>}
      </div>
    </section>;
  };

  return <section className="workspace-page workspace-browser-page">
    <div className="page-heading"><div><p className="eyebrow">OPERATIONS / WORKSPACE</p><h1>{text.title}</h1><span>{text.lead}</span></div><button className="secondary-button" onClick={refresh}><RefreshCw className={loadingDirs.size ? "spin" : ""} />{text.refresh}</button></div>
    {error && <div className="error-banner"><AlertTriangle /><div><strong>{text.loadFailed}</strong><span>{error}</span></div><button onClick={refresh}>{text.refresh}</button></div>}
    <div className="workspace-browser">
      <div className="workspace-columns" ref={columnsViewport}>{columnPaths.map(renderColumn)}</div>
      <div className="workspace-preview-panel">
        {!selected ? <div className="workspace-preview-empty"><HardDrive /><strong>{text.select}</strong><span>TXT · MD · JSON · YAML · CSV · PARQUET</span></div> : <>
          <header className="workspace-file-header"><div>{(() => { const Icon = entryIcon(selected); return <Icon />; })()}<span><strong>{selected.name}</strong><small>{selected.path}</small></span></div><div><span>{text.size}<strong>{formatBytes(selected.size)}</strong></span><span>{text.modified}<strong>{new Date(selected.modified_at * 1000).toLocaleString(language === "zh" ? "zh-CN" : "en")}</strong></span></div></header>
          {previewLoading ? <div className="workspace-preview-loading"><LoaderCircle className="spin" /></div> : previewError ? <div className="workspace-preview-message error"><AlertTriangle /><strong>{text.previewFailed}</strong><span>{previewError}</span></div> : preview && <PreviewContent preview={preview} text={text} onPage={(offset) => void loadPreview(selected, offset)} />}
        </>}
      </div>
    </div>
    {contextMenu && <div className="workspace-context-menu" role="menu" style={{ left: contextMenu.x, top: contextMenu.y }} onClick={(event) => event.stopPropagation()}>
      <header><span>{contextMenu.entry.name}</span><small>{contextMenu.entry.preview_kind || contextMenu.entry.kind}</small></header>
      {contextMenu.entry.kind === "file" && contextMenu.entry.supported && <button role="menuitem" onClick={() => { selectFile(contextMenu.entry, contextMenu.column); setContextMenu(null); }}><Eye />{text.previewAction}</button>}
      {contextMenu.entry.kind === "directory" && <button role="menuitem" onClick={() => { openDirectory(contextMenu.entry, contextMenu.column); setContextMenu(null); }}><ChevronRight />{text.open}</button>}
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
  if (preview.kind === "parquet") return <div className="workspace-parquet">
    <div className="parquet-summary">
      <article><small>{text.rowCount}</small><strong>{(preview.row_count ?? 0).toLocaleString()}</strong></article>
      <article><small>{text.fields}</small><strong>{preview.schema?.length ?? preview.columns?.length ?? 0}</strong></article>
      <article><small>{text.rowGroups}</small><strong>{preview.row_group_count ?? 0}</strong></article>
      <article><small>{text.size}</small><strong>{formatBytes(preview.size)}</strong></article>
    </div>
    <section className="parquet-schema"><header><Database /><strong>{text.schema}</strong></header><div>{(preview.schema || []).map((field) => <span key={field.name}><code>{field.name}</code><small>{field.type}</small>{field.nullable && <i>NULL</i>}</span>)}</div></section>
    <section className="parquet-sample"><header><FileSpreadsheet /><strong>{text.parquet}</strong><small>{text.sample}</small></header><DataTable columns={preview.columns || []} rows={preview.rows || []} /></section>
  </div>;
  if (preview.kind === "unsupported") return <div className="workspace-preview-message"><File /><strong>{text.unsupported}</strong></div>;
  if (preview.kind === "csv") {
    const offset = preview.offset || 0; const limit = preview.limit || 200;
    return <div className="workspace-csv"><div className="workspace-csv-scroll"><DataTable columns={preview.columns || []} rows={preview.rows || []} offset={offset} /></div><footer><span>{preview.rows?.length ? `${offset + 1}–${offset + preview.rows.length}` : "0"} {text.rows}</span><div><button disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - limit))}>{text.previous}</button><button disabled={!preview.has_more} onClick={() => onPage(offset + limit)}>{text.next}</button></div></footer></div>;
  }
  const structured = (preview.kind === "json" || preview.kind === "yaml") && !preview.parse_error && preview.data !== undefined;
  return <div className="workspace-document">
    {preview.truncated && <div className="workspace-notice"><AlertTriangle />{text.truncated}</div>}
    {preview.kind === "json" && preview.parse_error && <div className="workspace-notice error"><AlertTriangle /><strong>{text.invalidJson}</strong><span>{preview.parse_error}</span></div>}
    {preview.kind === "yaml" && preview.parse_error && <div className="workspace-notice error"><AlertTriangle /><strong>{text.invalidYaml}</strong><span>{preview.parse_error}</span></div>}
    {preview.kind === "markdown" && preview.frontmatter !== null && preview.frontmatter !== undefined && <section className="workspace-frontmatter"><header>{text.frontmatter}</header><pre>{JSON.stringify(preview.frontmatter, null, 2)}</pre></section>}
    {preview.kind === "markdown" && preview.frontmatter_error && <div className="workspace-notice error"><AlertTriangle />{preview.frontmatter_error}</div>}
    {preview.kind === "markdown" ? <article className="workspace-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span className="markdown-image-placeholder">[{alt || "image"}]</span>, a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a> }}>{preview.content || ""}</ReactMarkdown></article> : structured ? <StructuredTree value={preview.data} /> : <pre className="workspace-code">{preview.content || ""}</pre>}
  </div>;
}

function DataTable({ columns, rows, offset = 0 }: { columns: string[]; rows: unknown[][]; offset?: number }) {
  return <table><thead><tr><th>#</th>{columns.map((column, index) => <th key={`${column}-${index}`}>{column || `Column ${index + 1}`}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}><td>{offset + rowIndex + 1}</td>{columns.map((_, cellIndex) => <td key={cellIndex} title={String(row[cellIndex] ?? "")}>{String(row[cellIndex] ?? "")}</td>)}</tr>)}</tbody></table>;
}

function StructuredTree({ value }: { value: unknown }) {
  return <div className="structured-tree"><StructuredNode name="root" value={value} depth={0} /></div>;
}

function StructuredNode({ name, value, depth }: { name: string; value: unknown; depth: number }) {
  const [expanded, setExpanded] = useState(depth === 0);
  const isArray = Array.isArray(value); const isObject = value !== null && typeof value === "object";
  if (!isObject) {
    const type = value === null ? "null" : typeof value; const rendered = typeof value === "string" ? JSON.stringify(value) : String(value);
    return <div className="structured-leaf" style={{ "--tree-depth": depth } as React.CSSProperties}><span className="structured-key">{name}</span><i>:</i><span className={`structured-value ${type}`}>{rendered}</span></div>;
  }
  const entries = isArray ? value.map((item, index) => [`[${index}]`, item] as const) : Object.entries(value as Record<string, unknown>);
  return <div className="structured-node"><button type="button" className="structured-toggle" style={{ "--tree-depth": depth } as React.CSSProperties} aria-expanded={expanded} onClick={() => setExpanded((open) => !open)}>{expanded ? <span>−</span> : <ChevronRight />}<span className="structured-key">{name}</span><b>{isArray ? "List" : "Dict"}</b><small>{entries.length} {isArray ? "items" : "keys"}</small></button>{expanded && <div className="structured-children">{entries.map(([key, item]) => <StructuredNode key={key} name={key} value={item} depth={depth + 1} />)}</div>}</div>;
}
