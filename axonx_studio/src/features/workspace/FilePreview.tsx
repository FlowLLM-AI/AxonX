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
import type { Language, WorkspacePreview } from "../../types";

const copy = {
  zh: {
    unsupported: "暂不支持预览此文件",
    parquet: "Parquet 数据预览",
    sample: "前 5 行",
    rowCount: "总行数",
    rowGroups: "Row Groups",
    fields: "字段数",
    schema: "字段结构",
    truncated: "内容过大，仅展示前 512 KiB",
    invalidJson: "JSON 格式有误",
    invalidYaml: "YAML 格式有误",
    frontmatter: "Frontmatter",
    rows: "行",
    previous: "上一页",
    next: "下一页",
    size: "文件大小",
  },
  en: {
    unsupported: "Preview is not supported for this file",
    parquet: "Parquet data preview",
    sample: "First 5 rows",
    rowCount: "Rows",
    rowGroups: "Row groups",
    fields: "Fields",
    schema: "Schema",
    truncated: "Large file: showing the first 512 KiB",
    invalidJson: "Invalid JSON",
    invalidYaml: "Invalid YAML",
    frontmatter: "Frontmatter",
    rows: "rows",
    previous: "Previous",
    next: "Next",
    size: "File size",
  },
} as const;

export function FilePreview({
  preview,
  language,
  onPage,
}: {
  preview: WorkspacePreview;
  language: Language;
  onPage: (offset: number) => void;
}) {
  const text = copy[language];
  if (preview.kind === "parquet")
    return (
      <div className="workspace-parquet">
        <div className="parquet-summary">
          <article>
            <small>{text.rowCount}</small>
            <strong>{(preview.row_count ?? 0).toLocaleString()}</strong>
          </article>
          <article>
            <small>{text.fields}</small>
            <strong>
              {preview.schema?.length ?? preview.columns?.length ?? 0}
            </strong>
          </article>
          <article>
            <small>{text.rowGroups}</small>
            <strong>{preview.row_group_count ?? 0}</strong>
          </article>
          <article>
            <small>{text.size}</small>
            <strong>{formatBytes(preview.size)}</strong>
          </article>
        </div>
        <section className="parquet-schema">
          <header>
            <Database />
            <strong>{text.schema}</strong>
          </header>
          <div>
            {(preview.schema || []).map((field) => (
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
            <strong>{text.parquet}</strong>
            <small>{text.sample}</small>
          </header>
          <DataTable
            columns={preview.columns || []}
            rows={preview.rows || []}
          />
        </section>
      </div>
    );
  if (preview.kind === "unsupported")
    return (
      <div className="workspace-preview-message">
        <File />
        <strong>{text.unsupported}</strong>
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
            {text.rows}
          </span>
          <div>
            <button
              disabled={offset === 0}
              onClick={() => onPage(Math.max(0, offset - limit))}
            >
              {text.previous}
            </button>
            <button
              disabled={!preview.has_more}
              onClick={() => onPage(offset + limit)}
            >
              {text.next}
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
          {text.truncated}
        </div>
      )}
      {preview.kind === "json" && preview.parse_error && (
        <div className="workspace-notice error">
          <AlertTriangle />
          <strong>{text.invalidJson}</strong>
          <span>{preview.parse_error}</span>
        </div>
      )}
      {preview.kind === "yaml" && preview.parse_error && (
        <div className="workspace-notice error">
          <AlertTriangle />
          <strong>{text.invalidYaml}</strong>
          <span>{preview.parse_error}</span>
        </div>
      )}
      {preview.kind === "markdown" &&
        preview.frontmatter !== null &&
        preview.frontmatter !== undefined && (
          <section className="workspace-frontmatter">
            <header>{text.frontmatter}</header>
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
        <b>{isArray ? "List" : "Dict"}</b>
        <small>
          {entries.length} {isArray ? "items" : "keys"}
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
