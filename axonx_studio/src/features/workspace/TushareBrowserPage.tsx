import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Database,
  File,
  FileCode2,
  FileJson,
  FileSpreadsheet,
  FileText,
  Folder,
  HardDrive,
  LoaderCircle,
  RefreshCw,
} from "lucide-react";
import { RailResizer } from "../../shared/ui/RailResizer";
import { formatBytes } from "../../shared/lib/format";
import type { ContextOption } from "../../app/types";
import { useTranslation } from "react-i18next";
import type {
  WorkspaceDirectory,
  WorkspaceEntry,
  WorkspacePreview,
} from "./types";
import { listWorkspaceEntries, previewWorkspaceFile } from "./api";

const FilePreview = lazy(() =>
  import("./FilePreview").then((module) => ({ default: module.FilePreview })),
);

const ROOT = "tushare";

function iconFor(entry: WorkspaceEntry) {
  if (entry.kind === "directory") return Folder;
  if (entry.preview_kind === "markdown") return FileText;
  if (entry.preview_kind === "json" || entry.preview_kind === "yaml")
    return FileJson;
  if (entry.preview_kind === "csv") return FileSpreadsheet;
  if (entry.preview_kind === "parquet") return Database;
  if (entry.preview_kind === "text") return FileCode2;
  return File;
}

export default function TushareBrowserPage({
  remoteIp,
  initialPath,
  onConnection,
  onPathChange,
  onOptionsChange,
}: {
  remoteIp?: string;
  initialPath?: string;
  onConnection: (online: boolean) => void;
  onPathChange?: (path: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
}) {
  const { t } = useTranslation();
  const [directories, setDirectories] = useState<
    Record<string, WorkspaceDirectory>
  >({});
  const [expanded, setExpanded] = useState(() => new Set([ROOT]));
  const [loading, setLoading] = useState(() => new Set<string>());
  const [selected, setSelected] = useState<WorkspaceEntry | null>(null);
  const [preview, setPreview] = useState<WorkspacePreview | null>(null);
  const [error, setError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewRequest = useRef(0);

  const loadDirectory = useCallback(
    async (path: string, signal?: AbortSignal) => {
      setLoading((current) => new Set(current).add(path));
      try {
        const result = await listWorkspaceEntries(path, remoteIp, signal);
        setDirectories((current) => ({ ...current, [path]: result }));
        setError("");
        onConnection(true);
      } catch (reason) {
        if ((reason as { name?: string })?.name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : String(reason));
          onConnection(false);
        }
      } finally {
        setLoading((current) => {
          const next = new Set(current);
          next.delete(path);
          return next;
        });
      }
    },
    [remoteIp, onConnection],
  );

  const loadPreview = useCallback(
    async (entry: WorkspaceEntry, offset = 0) => {
      const request = ++previewRequest.current;
      setSelected(entry);
      setPreview(null);
      setPreviewError("");
      setPreviewLoading(true);
      try {
        const result = await previewWorkspaceFile(
          entry.path,
          offset,
          200,
          remoteIp,
        );
        if (request === previewRequest.current) {
          setPreview(result);
          onConnection(true);
        }
      } catch (reason) {
        if (request === previewRequest.current) {
          setPreviewError(
            reason instanceof Error ? reason.message : String(reason),
          );
          onConnection(false);
        }
      } finally {
        if (request === previewRequest.current) setPreviewLoading(false);
      }
    },
    [remoteIp, onConnection],
  );

  const selectFile = useCallback(
    (entry: WorkspaceEntry) => {
      onPathChange?.(entry.path);
      void loadPreview(entry);
    },
    [loadPreview, onPathChange],
  );

  const toggleFolder = useCallback(
    (entry: WorkspaceEntry) => {
      setExpanded((current) => {
        const next = new Set(current);
        if (next.has(entry.path)) next.delete(entry.path);
        else next.add(entry.path);
        return next;
      });
      onPathChange?.(entry.path);
      if (!directories[entry.path]) void loadDirectory(entry.path);
    },
    [directories, loadDirectory, onPathChange],
  );

  const refresh = useCallback(() => {
    previewRequest.current += 1;
    setDirectories({});
    setExpanded(new Set([ROOT]));
    setSelected(null);
    setPreview(null);
    setPreviewError("");
    setError("");
    void loadDirectory(ROOT);
  }, [loadDirectory]);

  useEffect(() => {
    const controller = new AbortController();
    setDirectories({});
    setExpanded(new Set([ROOT]));
    setSelected(null);
    setPreview(null);
    setError("");
    void loadDirectory(ROOT, controller.signal);
    return () => {
      controller.abort();
      previewRequest.current += 1;
    };
  }, [remoteIp, loadDirectory]);

  useEffect(() => {
    if (!initialPath || !initialPath.startsWith(ROOT) || initialPath === ROOT)
      return;
    let alive = true;
    const reveal = async () => {
      try {
        const parts = initialPath.split("/").filter(Boolean);
        const loaded: Record<string, WorkspaceDirectory> = {};
        const open = new Set([ROOT]);
        let parent = ROOT;
        let target: WorkspaceEntry | undefined;
        for (const part of parts.slice(1)) {
          const directory =
            loaded[parent] || (await listWorkspaceEntries(parent, remoteIp));
          loaded[parent] = directory;
          target = directory.entries.find((entry) => entry.name === part);
          if (!target) return;
          if (target.kind === "directory") {
            parent = target.path;
            open.add(parent);
          }
        }
        if (!alive || !target) return;
        if (target.kind === "directory")
          loaded[target.path] = await listWorkspaceEntries(
            target.path,
            remoteIp,
          );
        setDirectories((current) => ({ ...current, ...loaded }));
        setExpanded(open);
        onConnection(true);
        if (target.kind === "file") void loadPreview(target);
      } catch (reason) {
        if (alive) {
          setError(reason instanceof Error ? reason.message : String(reason));
          onConnection(false);
        }
      }
    };
    void reveal();
    return () => {
      alive = false;
    };
  }, [initialPath, remoteIp, loadPreview, onConnection]);

  useEffect(() => {
    const options = new Map<string, ContextOption>();
    Object.values(directories)
      .flatMap((directory) => directory.entries)
      .filter((entry) => entry.kind !== "symlink")
      .forEach((entry) =>
        options.set(entry.path, {
          value: entry.path,
          label: entry.name,
          detail:
            entry.kind === "directory"
              ? t("workspace.folder")
              : entry.preview_kind || "File",
        }),
      );
    onOptionsChange?.([...options.values()]);
  }, [directories, onOptionsChange, t]);

  const renderEntries = (path: string, depth: number): React.ReactNode => {
    const directory = directories[path];
    if (!directory && loading.has(path))
      return (
        <div
          className="tushare-tree-loading"
          style={{ "--tree-level": depth } as React.CSSProperties}
        >
          <LoaderCircle className="spin" />
        </div>
      );
    if (!directory) return null;
    const entries = [...directory.entries].sort(
      (a, b) =>
        Number(b.kind === "directory") - Number(a.kind === "directory") ||
        a.name.localeCompare(b.name),
    );
    return entries.length ? (
      entries.map((entry) => {
        const Icon = iconFor(entry);
        const folder = entry.kind === "directory";
        const open = expanded.has(entry.path);
        return (
          <div className="tushare-tree-node" key={entry.path}>
            <button
              className={selected?.path === entry.path ? "active" : ""}
              style={{ "--tree-level": depth } as React.CSSProperties}
              onClick={() =>
                folder
                  ? toggleFolder(entry)
                  : entry.kind === "file" && selectFile(entry)
              }
              disabled={entry.kind === "symlink"}
              title={entry.path}
            >
              <span className="tree-disclosure">
                {folder ? open ? <ChevronDown /> : <ChevronRight /> : null}
              </span>
              <Icon />
              <span>{entry.name}</span>
              {entry.kind === "file" && (
                <small>{formatBytes(entry.size)}</small>
              )}
            </button>
            {folder && open && renderEntries(entry.path, depth + 1)}
          </div>
        );
      })
    ) : (
      <div
        className="tushare-tree-empty"
        style={{ "--tree-level": depth } as React.CSSProperties}
      >
        {t("workspace.empty")}
      </div>
    );
  };

  return (
    <section className="workspace-page workspace-browser-page">
      {error && (
        <div className="error-banner">
          <AlertTriangle />
          <div>
            <strong>{t("workspace.loadFailed")}</strong>
            <span>{error}</span>
          </div>
          <button onClick={refresh}>{t("refresh")}</button>
        </div>
      )}
      <div className="workspace-browser tushare-browser">
        <aside className="workspace-explorer tushare-tree-panel">
          <header>
            <div>
              <Folder />
              <span>
                <strong>tushare</strong>
                <small>workspace_dir/tushare</small>
              </span>
            </div>
            <button onClick={refresh} aria-label={t("refresh")}>
              <RefreshCw className={loading.has(ROOT) ? "spin" : ""} />
            </button>
          </header>
          <nav>{renderEntries(ROOT, 0)}</nav>
        </aside>
        <RailResizer min={180} max={520} className="context-resizer" />
        <div className="workspace-preview-panel">
          {!selected ? (
            <div className="workspace-preview-empty">
              <div>
                <HardDrive />
              </div>
              <small>FILE PREVIEW</small>
              <strong>{t("workspace.select")}</strong>
              <span>
                CSV&nbsp;&nbsp;·&nbsp;&nbsp;PARQUET&nbsp;&nbsp;·&nbsp;&nbsp;JSON
              </span>
            </div>
          ) : (
            <>
              <header className="workspace-file-header">
                <div>
                  {(() => {
                    const Icon = iconFor(selected);
                    return <Icon />;
                  })()}
                  <span>
                    <strong>{selected.name}</strong>
                    <small>{selected.path}</small>
                  </span>
                </div>
                <div>
                  <span>
                    {t("workspace.size")}
                    <strong>{formatBytes(selected.size)}</strong>
                  </span>
                </div>
              </header>
              {previewLoading ? (
                <div className="workspace-preview-loading">
                  <LoaderCircle className="spin" />
                </div>
              ) : previewError ? (
                <div className="workspace-preview-message error">
                  <AlertTriangle />
                  <strong>{t("workspace.previewFailed")}</strong>
                  <span>{previewError}</span>
                </div>
              ) : (
                preview && (
                  <Suspense
                    fallback={
                      <div className="workspace-preview-loading">
                        <LoaderCircle className="spin" />
                      </div>
                    }
                  >
                    <FilePreview
                      preview={preview}
                      onPage={(offset) => void loadPreview(selected, offset)}
                    />
                  </Suspense>
                )
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
