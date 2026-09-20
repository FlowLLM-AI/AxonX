import { useState } from "react";
import {
  AlertTriangle,
  ChevronRight,
  Database,
  File,
  FileSpreadsheet,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatBytes } from "../../shared/lib/format";
import { useTranslation } from "react-i18next";
import type { WorkspacePreview } from "./types";

export function FilePreview({
  preview,
  onPage,
}: {
  preview: WorkspacePreview;
  onPage: (offset: number) => void;
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
      {preview.kind === "markdown" &&
        preview.frontmatter !== null &&
        preview.frontmatter !== undefined && (
          <section className="workspace-frontmatter">
            <header>{t("workspacePreview.frontmatter")}</header>
            <pre>{JSON.stringify(preview.frontmatter, null, 2)}</pre>
          </section>
        )}
      {preview.kind === "markdown" && preview.frontmatter_error && (
        <div className="workspace-notice error">
          <AlertTriangle />
          {preview.frontmatter_error}
        </div>
      )}
      {preview.kind === "markdown" ? (
        <article className="workspace-markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              img: ({ alt }) => (
                <span className="markdown-image-placeholder">
                  [{alt || "image"}]
                </span>
              ),
              a: ({ children, ...props }) => (
                <a {...props} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {preview.content || ""}
          </ReactMarkdown>
        </article>
      ) : structured ? (
        <StructuredTree value={preview.data} />
      ) : (
        <pre className="workspace-code">{preview.content || ""}</pre>
      )}
    </div>
  );
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
