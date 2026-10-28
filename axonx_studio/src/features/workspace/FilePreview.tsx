import {
  AlertTriangle,
  ChevronRight,
  Database,
  File,
  FileSpreadsheet,
  FileCode2,
  Eye,
  LoaderCircle,
} from "lucide-react";
import type { Nodes, Root } from "mdast";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { routeHash } from "../../app/routes";
import type { MarkdownPreview } from "../../shared/api/contracts";
import type {
  WorkspacePreview,
  WorkspaceText,
} from "../../shared/api/workspace";
import { formatBytes } from "../../shared/lib/format";

export function FilePreview({
  preview,
  onPage,
  previousOffset,
  onReadSource,
  path = "",
  machineId = "local",
}: {
  preview: WorkspacePreview;
  onPage: (offset: number) => void;
  previousOffset: number;
  onReadSource?: (signal: AbortSignal) => Promise<WorkspaceText>;
  path?: string;
  machineId?: string;
}) {
  const { t } = useTranslation();
  if (preview.kind === "parquet") {
    const offset = preview.offset || 0;
    const limit = preview.limit || 200;
    return (
      <div className="workspace-parquet">
        <div className="parquet-summary">
          <article>
            <small>{t("workspacePreview.rowCount")}</small>
            <strong>{(preview.row_count ?? 0).toLocaleString()}</strong>
          </article>
          <article>
            <small>{t("workspacePreview.fields")}</small>
            <strong>
              {preview.column_schema?.length ?? preview.columns?.length ?? 0}
            </strong>
          </article>
          <article>
            <small>{t("workspacePreview.rowGroups")}</small>
            <strong>{preview.row_group_count ?? 0}</strong>
          </article>
          <article>
            <small>{t("workspacePreview.size")}</small>
            <strong>{formatBytes(preview.size)}</strong>
          </article>
        </div>
        <section className="parquet-schema">
          <header>
            <Database />
            <strong>{t("workspacePreview.schema")}</strong>
          </header>
          <div>
            {(preview.column_schema || []).map((field) => (
              <span key={field.name}>
                <code>{field.name}</code>
                <small>{field.type}</small>
                {field.nullable && <i>NULL</i>}
              </span>
            ))}
          </div>
        </section>
        <section className="parquet-sample">
          <header>
            <FileSpreadsheet />
            <strong>{t("workspacePreview.parquet")}</strong>
            <small>
              {preview.rows?.length
                ? `${offset + 1}–${offset + preview.rows.length}`
                : "0"}{" "}
              {t("workspacePreview.rows")}
            </small>
          </header>
          <DataTable
            columns={preview.columns || []}
            rows={preview.rows || []}
            offset={offset}
          />
          <footer>
            <button
              disabled={offset === 0}
              onClick={() => onPage(Math.max(0, offset - limit))}
            >
              {t("workspacePreview.previous")}
            </button>
            <button
              disabled={!preview.has_more}
              onClick={() => onPage(offset + limit)}
            >
              {t("workspacePreview.next")}
            </button>
          </footer>
        </section>
      </div>
    );
  }
  if (preview.kind === "unsupported")
    return (
      <div className="workspace-preview-message">
        <File />
        <strong>{t("workspacePreview.unsupported")}</strong>
      </div>
    );
  if (preview.kind === "jsonl") {
    return (
      <div className="workspace-document">
        {preview.truncated && (
          <div className="workspace-notice">
            <AlertTriangle />
            {t("workspacePreview.truncated")}
          </div>
        )}
        {!preview.rows.length && (
          <p className="muted">{t("workspacePreview.emptyJsonl")}</p>
        )}
        {preview.rows.map((row) => (
          <section className="workspace-jsonl-record" key={row.line}>
            <header>{t("workspacePreview.line", { line: row.line })}</header>
            {row.truncated ? (
              <pre className="workspace-code">{row.content}</pre>
            ) : row.parse_error ? (
              <>
                <div className="workspace-notice error">
                  <AlertTriangle />
                  <strong>{t("workspacePreview.invalidJson")}</strong>
                  <span>{row.parse_error}</span>
                </div>
                <pre className="workspace-code">{row.content}</pre>
              </>
            ) : (
              <StructuredTree value={row.data} />
            )}
          </section>
        ))}
        <footer className="workspace-jsonl-pagination">
          <button
            disabled={preview.offset === 0}
            onClick={() => onPage(previousOffset)}
          >
            {t("workspacePreview.previous")}
          </button>
          <button
            disabled={!preview.has_more}
            onClick={() => onPage(preview.offset + preview.rows.length)}
          >
            {t("workspacePreview.next")}
          </button>
        </footer>
      </div>
    );
  }
  if (preview.kind === "csv") {
    const offset = preview.offset || 0;
    const limit = preview.limit || 200;
    return (
      <div className="workspace-csv">
        <div className="workspace-csv-scroll">
          <DataTable
            columns={preview.columns || []}
            rows={preview.rows || []}
            offset={offset}
          />
        </div>
        <footer>
          <span>
            {preview.rows?.length
              ? `${offset + 1}–${offset + preview.rows.length}`
              : "0"}{" "}
            {t("workspacePreview.rows")}
          </span>
          <div>
            <button
              disabled={offset === 0}
              onClick={() => onPage(Math.max(0, offset - limit))}
            >
              {t("workspacePreview.previous")}
            </button>
            <button
              disabled={!preview.has_more}
              onClick={() => onPage(offset + limit)}
            >
              {t("workspacePreview.next")}
            </button>
          </div>
        </footer>
      </div>
    );
  }
  if (preview.kind === "markdown")
    return (
      <MarkdownDocument
        preview={preview}
        onReadSource={onReadSource}
        path={path}
        machineId={machineId}
      />
    );
  const structured =
    (preview.kind === "json" || preview.kind === "yaml") &&
    !preview.parse_error &&
    preview.data !== undefined;
  return (
    <div className="workspace-document">
      {preview.truncated && (
        <div className="workspace-notice">
          <AlertTriangle />
          {t("workspacePreview.truncated")}
        </div>
      )}
      {preview.kind === "json" && preview.parse_error && (
        <div className="workspace-notice error">
          <AlertTriangle />
          <strong>{t("workspacePreview.invalidJson")}</strong>
          <span>{preview.parse_error}</span>
        </div>
      )}
      {preview.kind === "yaml" && preview.parse_error && (
        <div className="workspace-notice error">
          <AlertTriangle />
          <strong>{t("workspacePreview.invalidYaml")}</strong>
          <span>{preview.parse_error}</span>
        </div>
      )}
      {structured ? (
        <StructuredTree value={preview.data} />
      ) : (
        <pre className="workspace-code">{preview.content || ""}</pre>
      )}
    </div>
  );
}

function MarkdownDocument({
  preview,
  onReadSource,
  path,
  machineId,
}: {
  preview: MarkdownPreview;
  onReadSource?: (signal: AbortSignal) => Promise<WorkspaceText>;
  path: string;
  machineId: string;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<"preview" | "source">("preview");
  const [attempt, retry] = useState(0);
  const [source, setSource] = useState<{
    data: WorkspaceText | null;
    loading: boolean;
    error: string;
  }>({ data: null, loading: false, error: "" });
  useEffect(() => {
    if (mode !== "source" || source.data || !onReadSource) return;
    const controller = new AbortController();
    setSource({ data: null, loading: true, error: "" });
    void Promise.resolve()
      .then(() => onReadSource(controller.signal))
      .then(
        (data) => {
          if (!controller.signal.aborted)
            setSource({ data, loading: false, error: "" });
        },
        (reason) => {
          if (!controller.signal.aborted)
            setSource({
              data: null,
              loading: false,
              error: reason instanceof Error ? reason.message : String(reason),
            });
        },
      );
    return () => controller.abort();
  }, [mode, onReadSource, source.data, attempt]);
  return (
    <div className="workspace-document">
      <div
        className="workspace-markdown-toolbar"
        role="group"
        aria-label={t("workspacePreview.markdownView")}
      >
        <button
          type="button"
          aria-pressed={mode === "preview"}
          onClick={() => setMode("preview")}
        >
          <Eye />
          {t("workspacePreview.preview")}
        </button>
        <button
          type="button"
          aria-pressed={mode === "source"}
          disabled={!onReadSource}
          onClick={() => setMode("source")}
        >
          <FileCode2 />
          {t("workspacePreview.source")}
        </button>
      </div>
      {(mode === "source" ? source.data?.truncated : preview.truncated) && (
        <div className="workspace-notice">
          <AlertTriangle />
          {t("workspacePreview.truncated")}
        </div>
      )}
      {mode === "source" ? (
        source.loading ? (
          <div className="workspace-preview-loading">
            <LoaderCircle className="spin" />
          </div>
        ) : source.error ? (
          <div className="workspace-notice error" role="alert">
            <AlertTriangle />
            {t("workspacePreview.sourceFailed")}
            <span>{source.error}</span>
            <button onClick={() => retry((attempt) => attempt + 1)}>
              {t("retry")}
            </button>
          </div>
        ) : (
          <pre className="workspace-code">{source.data?.content}</pre>
        )
      ) : (
        <>
          {preview.frontmatter !== null &&
            preview.frontmatter !== undefined && (
              <section className="workspace-frontmatter">
                <header>{t("workspacePreview.frontmatter")}</header>
                <StructuredTree value={preview.frontmatter} />
              </section>
            )}
          {preview.frontmatter_error && (
            <div className="workspace-notice error">
              <AlertTriangle />
              {preview.frontmatter_error}
            </div>
          )}
          <article className="workspace-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkHeadings]}
              components={{
                img: ({ alt }) => (
                  <span className="markdown-image-placeholder">
                    [{alt || "image"}]
                  </span>
                ),
                a: ({ children, href }) => {
                  const external = /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(
                    href || "",
                  );
                  return (
                    <a
                      href={
                        external ? href : workspaceLink(href, path, machineId)
                      }
                      target={external ? "_blank" : undefined}
                      rel={external ? "noreferrer" : undefined}
                      onClick={(event) => {
                        if (!href?.startsWith("#")) return;
                        event.preventDefault();
                        const fragment = href.slice(1);
                        const headings = event.currentTarget
                          .closest("article")
                          ?.querySelectorAll("[id]");
                        Array.from(headings || [])
                          .find(
                            (heading) =>
                              heading.id === fragment ||
                              encodeURIComponent(heading.id) === fragment,
                          )
                          ?.scrollIntoView({ block: "start" });
                      }}
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {preview.content}
            </ReactMarkdown>
          </article>
        </>
      )}
    </div>
  );
}

function markdownText(node: Nodes): string {
  if (node.type === "text" || node.type === "inlineCode") return node.value;
  if (node.type === "image") return node.alt || "";
  return "children" in node ? node.children.map(markdownText).join("") : "";
}

function remarkHeadings() {
  return (tree: Root) => {
    const ids = new Set<string>();
    const visit = (node: Nodes) => {
      if (node.type === "heading") {
        const base = markdownText(node)
          .trim()
          .toLowerCase()
          .replace(/[^\p{L}\p{N}\s_-]/gu, "")
          .replace(/\s/g, "-");
        let id = base;
        for (let suffix = 1; ids.has(id); suffix++) id = `${base}-${suffix}`;
        ids.add(id);
        node.data = {
          ...node.data,
          hProperties: { ...node.data?.hProperties, id },
        };
      }
      if ("children" in node) node.children.forEach(visit);
    };
    visit(tree);
  };
}

function workspaceLink(
  href: string | undefined,
  path: string,
  machineId: string,
) {
  if (!href || href.startsWith("#")) return href;
  try {
    const base = path.split("/").map(encodeURIComponent).join("/");
    const url = new URL(href, `https://workspace.invalid/${base}`);
    return routeHash(machineId, {
      section: "workspace",
      view: "files",
      resource: decodeURIComponent(url.pathname.slice(1)),
    });
  } catch {
    return undefined;
  }
}

function DataTable({
  columns,
  rows,
  offset = 0,
}: {
  columns: string[];
  rows: unknown[][];
  offset?: number;
}) {
  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          {columns.map((column, index) => (
            <th key={`${column}-${index}`}>
              {column || `Column ${index + 1}`}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            <td>{offset + rowIndex + 1}</td>
            {columns.map((_, cellIndex) => (
              <td key={cellIndex} title={String(row[cellIndex] ?? "")}>
                {String(row[cellIndex] ?? "")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StructuredTree({ value }: { value: unknown }) {
  return (
    <div className="structured-tree">
      <StructuredNode name="root" value={value} depth={0} />
    </div>
  );
}

function StructuredNode({
  name,
  value,
  depth,
}: {
  name: string;
  value: unknown;
  depth: number;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(depth === 0);
  const isArray = Array.isArray(value);
  const isObject = value !== null && typeof value === "object";
  if (!isObject) {
    const type = value === null ? "null" : typeof value;
    const rendered =
      typeof value === "string" ? JSON.stringify(value) : String(value);
    return (
      <div
        className="structured-leaf"
        style={{ "--tree-depth": depth } as React.CSSProperties}
      >
        <span className="structured-key">{name}</span>
        <i>:</i>
        <span className={`structured-value ${type}`}>{rendered}</span>
      </div>
    );
  }
  const entries = isArray
    ? value.map((item, index) => [`[${index}]`, item] as const)
    : Object.entries(value as Record<string, unknown>);
  return (
    <div className="structured-node">
      <button
        type="button"
        className="structured-toggle"
        style={{ "--tree-depth": depth } as React.CSSProperties}
        aria-expanded={expanded}
        onClick={() => setExpanded((open) => !open)}
      >
        {expanded ? <span>−</span> : <ChevronRight />}
        <span className="structured-key">{name}</span>
        <b>
          {isArray ? t("workspacePreview.list") : t("workspacePreview.dict")}
        </b>
        <small>
          {entries.length}{" "}
          {isArray ? t("workspacePreview.items") : t("workspacePreview.keys")}
        </small>
      </button>
      {expanded && (
        <div className="structured-children">
          {entries.map(([key, item]) => (
            <StructuredNode
              key={key}
              name={key}
              value={item}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
