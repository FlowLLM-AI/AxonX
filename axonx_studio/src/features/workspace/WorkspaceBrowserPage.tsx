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
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import type {
  WorkspaceEntry,
  WorkspaceListing,
} from "../../shared/api/contracts";
import type { WorkspacePreview } from "../../shared/api/workspace";
import {
  getWorkspaceRoot,
  listWorkspaceEntries,
  previewWorkspaceFile,
  readWorkspaceText,
} from "../../shared/api/workspace";
import { formatBytes } from "../../shared/lib/format";
import { RailResizer } from "../../shared/ui/RailResizer";

const FilePreview = lazy(() =>
  import("./FilePreview").then((module) => ({ default: module.FilePreview })),
);

const ROOT = "";

function iconFor(entry: WorkspaceEntry) {
  if (entry.kind === "directory") return Folder;
  if (entry.preview_kind === "markdown") return FileText;
  if (
    entry.preview_kind === "json" ||
    entry.preview_kind === "jsonl" ||
    entry.preview_kind === "yaml"
  )
    return FileJson;
  if (entry.preview_kind === "csv") return FileSpreadsheet;
  if (entry.preview_kind === "parquet") return Database;
  if (entry.preview_kind === "text") return FileCode2;
  return File;
}

export default function WorkspaceBrowserPage({
  target,
  machineId = "local",
  initialPath = ROOT,
  onConnection,
  onPathChange,
  onOptionsChange,
}: {
  target?: string;
  machineId?: string;
  initialPath?: string;
  onConnection: (online: boolean) => void;
  onPathChange: (path: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
}) {
  const { t } = useTranslation();
  const cache = useRef(new Map<string, WorkspaceListing>());
  const requests = useRef(new Set<AbortController>());
  const [directories, setDirectories] = useState<
    Record<string, WorkspaceListing>
  >({});
  const [expanded, setExpanded] = useState(new Set([ROOT]));
  const [loading, setLoading] = useState(new Set<string>());
  const [selected, setSelected] = useState<WorkspaceEntry | null>(null);
  const [preview, setPreview] = useState<WorkspacePreview | null>(null);
  const [error, setError] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [pageOffsets, setPageOffsets] = useState([0]);
  const offset = pageOffsets[pageOffsets.length - 1];
  const [revision, setRevision] = useState(0);
  const readSource = useCallback(
    (signal: AbortSignal) => {
      const root = cache.current.get(ROOT)?.workspace_root;
      if (!selected || !root) throw new Error("Workspace file is unavailable");
      return readWorkspaceText(
        { path: selected.path, workspaceRoot: root },
        { target, signal },
      );
    },
    [selected, target],
  );

  const loadDirectory = useCallback(
    async (path: string, signal: AbortSignal, append = false) => {
      const existing = cache.current.get(path);
      if (existing && !append) return existing;
      setLoading((current) => new Set(current).add(path));
      try {
        const result = await listWorkspaceEntries(
          { path, offset: append ? existing?.entries.length : 0 },
          { target, signal },
        );
        signal.throwIfAborted();
        const directory = {
          ...result,
          entries: append
            ? [...(existing?.entries || []), ...result.entries]
            : result.entries,
        };
        cache.current.set(path, directory);
        setDirectories(Object.fromEntries(cache.current));
        return directory;
      } finally {
        if (!signal.aborted)
          setLoading((current) => {
            const next = new Set(current);
            next.delete(path);
            return next;
          });
      }
    },
    [target],
  );

  useEffect(() => {
    const controller = new AbortController();
    const pending = requests.current;
    for (const request of pending) request.abort();
    pending.clear();
    pending.add(controller);
    setLoading(new Set());
    setSelected(null);
    setPageOffsets([0]);
    setError("");
    const reveal = async () => {
      let directory = await loadDirectory(ROOT, controller.signal);
      const open = new Set([ROOT]);
      let entry: WorkspaceEntry | undefined;
      let relativePath = initialPath;
      if (initialPath.startsWith("/")) {
        const workspaceRoot =
          directory.workspace_root ||
          (await getWorkspaceRoot({ target, signal: controller.signal }));
        controller.signal.throwIfAborted();
        const root = workspaceRoot?.replace(/\/+$/, "");
        if (!root || !initialPath.startsWith(`${root}/`))
          throw new Error(
            t("workspace.pathUnavailable", { path: initialPath }),
          );
        relativePath = initialPath.slice(root.length + 1);
      }
      const parts = relativePath.split("/").filter(Boolean);
      for (const [index, part] of parts.entries()) {
        entry = directory.entries.find((item) => item.name === part);
        while (!entry && directory.truncated) {
          directory = await loadDirectory(
            directory.path,
            controller.signal,
            true,
          );
          entry = directory.entries.find((item) => item.name === part);
        }
        if (
          !entry ||
          entry.kind === "symlink" ||
          (index < parts.length - 1 && entry.kind !== "directory")
        ) {
          throw new Error(
            t("workspace.pathUnavailable", { path: initialPath }),
          );
        }
        if (entry.kind === "directory") {
          open.add(entry.path);
          directory = await loadDirectory(entry.path, controller.signal);
        }
      }
      controller.signal.throwIfAborted();
      setExpanded((current) => new Set([...current, ...open]));
      setSelected(entry || null);
      onConnection(true);
    };
    void reveal().catch((reason) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
      }
    });
    return () => {
      controller.abort();
      pending.delete(controller);
    };
  }, [initialPath, revision, loadDirectory, onConnection, t, target]);

  useEffect(() => {
    const controller = new AbortController();
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(selected?.kind === "file");
    if (selected?.kind === "file") {
      void previewWorkspaceFile(
        { path: selected.path, offset, limit: 200 },
        { target, signal: controller.signal },
      )
        .then((result) => {
          if (!controller.signal.aborted) {
            setPreview(result);
            onConnection(true);
          }
        })
        .catch((reason) => {
          if (!controller.signal.aborted) {
            setPreviewError(
              reason instanceof Error ? reason.message : String(reason),
            );
            onConnection(false);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setPreviewLoading(false);
        });
    }
    return () => controller.abort();
  }, [selected, offset, target, onConnection]);

  useEffect(() => {
    const pending = requests.current;
    return () => {
      for (const controller of pending) controller.abort();
    };
  }, []);

  const loadMore = async (path: string) => {
    if (loading.has(path)) return;
    const controller = new AbortController();
    requests.current.add(controller);
    try {
      await loadDirectory(path, controller.signal, true);
      controller.signal.throwIfAborted();
      setError("");
      onConnection(true);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : String(reason));
        onConnection(false);
      }
    } finally {
      requests.current.delete(controller);
    }
  };

  const selectFile = (entry: WorkspaceEntry) => onPathChange(entry.path);
  const toggleFolder = (entry: WorkspaceEntry) => {
    if (expanded.has(entry.path))
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(entry.path);
        return next;
      });
    else {
      setExpanded((current) => new Set(current).add(entry.path));
      onPathChange(entry.path);
    }
  };
  const refresh = () => {
    for (const controller of requests.current) controller.abort();
    requests.current.clear();
    cache.current.clear();
    setDirectories({});
    setExpanded(new Set([ROOT]));
    setRevision((current) => current + 1);
  };

  useEffect(() => {
    onOptionsChange?.(
      Object.values(directories)
        .flatMap((directory) => directory.entries)
        .filter((entry) => entry.kind !== "symlink")
        .map((entry) => ({
          value: entry.path,
          kind: entry.kind === "directory" ? "directory" : "file",
          label: entry.name,
          detail:
            entry.kind === "directory"
              ? t("workspace.folder")
              : entry.preview_kind || t("workspace.file"),
        })),
    );
  }, [directories, onOptionsChange, t]);

  const renderEntries = (path: string, depth: number): React.ReactNode => {
    const directory = directories[path];
    if (!directory && loading.has(path))
      return (
        <div
          className="workspace-tree-loading"
          style={{ "--tree-level": depth } as React.CSSProperties}
        >
          <LoaderCircle className="spin" />
        </div>
      );
    if (!directory) return null;
    const entries = directory.entries;
    return (
      <>
        {entries.length ? (
          entries.map((entry) => {
            const Icon = iconFor(entry);
            const folder = entry.kind === "directory";
            const open = expanded.has(entry.path);
            return (
              <div className="workspace-tree-node" key={entry.path}>
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
                  aria-expanded={folder ? open : undefined}
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
            className="workspace-tree-empty"
            style={{ "--tree-level": depth } as React.CSSProperties}
          >
            {t("workspace.empty")}
          </div>
        )}
        {directory.truncated && (
          <button
            className="workspace-tree-more"
            disabled={loading.has(path)}
            onClick={() => void loadMore(path)}
          >
            {t("workspace.loadMore")}
          </button>
        )}
      </>
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
      <div className="workspace-browser">
        <aside className="workspace-explorer workspace-tree-panel">
          <header>
            <div>
              <Folder />
              <span>
                <strong>
                  <button
                    className="workspace-root"
                    onClick={() => onPathChange(ROOT)}
                  >
                    {t("shell.navigation.workspace")}
                  </button>
                </strong>
                <small>workspace_dir</small>
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
          {selected?.kind !== "file" ? (
            <div className="workspace-preview-empty">
              <div>
                <HardDrive />
              </div>
              <small>{t("shell.filePreview")}</small>
              <strong>{t("workspace.select")}</strong>
              <span>
                CSV&nbsp;&nbsp;·&nbsp;&nbsp;PARQUET&nbsp;&nbsp;·&nbsp;&nbsp;JSON&nbsp;&nbsp;·&nbsp;&nbsp;JSONL
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
                      key={`${selected.path}:${revision}`}
                      preview={preview}
                      path={selected.path}
                      machineId={machineId}
                      onReadSource={readSource}
                      previousOffset={pageOffsets[pageOffsets.length - 2] ?? 0}
                      onPage={(nextOffset) =>
                        setPageOffsets((pages) =>
                          nextOffset < offset
                            ? pages.slice(0, -1)
                            : [...pages, nextOffset],
                        )
                      }
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
