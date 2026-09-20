import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Braces,
  CheckCircle2,
  LoaderCircle,
  Network,
  Play,
  Search,
} from "lucide-react";
import { RailResizer } from "../../shared/ui/RailResizer";
import {
  initialSchemaValues,
  parseSchemaValues,
} from "../../shared/schema/values";
import type { SchemaFormValues } from "../../shared/schema/values";
import { SchemaField } from "../../shared/ui/SchemaForm/SchemaField";
import type { ContextOption, Language } from "../../app/types";
import type { MachineNode } from "../machines/types";
import type { JobInfo } from "./types";
import { invokeApi, listJobs } from "./api";

export function ApiWorkspace({
  language,
  machine,
  initialName,
  onSelected,
  onOptionsChange,
  onConnection,
}: {
  language: Language;
  machine: MachineNode;
  initialName?: string;
  onSelected: (name: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const zh = language === "zh";
  const [apis, setApis] = useState<JobInfo[]>([]);
  const [selectedName, setSelectedName] = useState(initialName || "");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState<SchemaFormValues>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<unknown>();

  const load = useCallback(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    listJobs(machine.isLocal ? undefined : machine.address, controller.signal)
      .then((catalog) => {
        const items = catalog.items;
        setApis(items);
        setSelectedName((current) =>
          items.some((item) => item.name === current) ? current : "",
        );
        onConnection(true);
      })
      .catch((reason) => {
        if (reason?.name !== "AbortError") {
          setError(String(reason));
          onConnection(false);
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [machine.address, machine.isLocal, onConnection]);
  useEffect(load, [load]);
  useEffect(() => {
    if (initialName && apis.some((item) => item.name === initialName))
      setSelectedName(initialName);
  }, [initialName, apis]);
  useEffect(() => {
    onOptionsChange?.(
      apis.map((api) => ({ value: api.name, label: api.name, detail: "POST" })),
    );
  }, [apis, onOptionsChange]);

  const selected = apis.find((item) => item.name === selectedName);
  const visible = useMemo(
    () =>
      apis.filter((item) =>
        `${item.name} ${item.description}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [apis, query],
  );
  useEffect(() => {
    if (!selected) return;
    setValues(initialSchemaValues(selected.input_schema));
    setResult(undefined);
    setError("");
  }, [selected]);

  const choose = (name: string) => {
    setSelectedName(name);
    onSelected(name);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const parsed = parseSchemaValues(selected.input_schema, values, {
      required: zh ? "必填" : "Required",
      invalidJson: zh ? "请输入合法 JSON" : "Enter valid JSON",
    });
    if (Object.keys(parsed.errors).length) {
      setError(Object.values(parsed.errors)[0]);
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      setResult(
        await invokeApi(
          selected.name,
          parsed.data,
          machine.isLocal ? undefined : machine.address,
        ),
      );
      onConnection(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="api-workspace unified-workspace">
      <aside className="context-rail api-index rail-panel">
        <header className="rail-header">
          <div className="rail-heading">
            <small>PUBLIC API</small>
            <strong>{zh ? "接口" : "Interfaces"}</strong>
          </div>
          <em>{apis.length}</em>
        </header>
        <label className="context-search rail-search">
          <Search />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={zh ? "搜索 API" : "Search APIs"}
          />
        </label>
        <nav className="rail-scroll">
          {loading && !apis.length ? (
            <LoaderCircle className="spin context-loader" />
          ) : (
            visible.map((api) => (
              <button
                key={api.name}
                className={`rail-list-item${selectedName === api.name ? " active" : ""}`}
                onClick={() => choose(api.name)}
              >
                <Network />
                <span className="rail-item-copy">
                  <strong>{api.name}</strong>
                  <small>POST /jobs/{api.name}</small>
                </span>
                <ArrowRight />
              </button>
            ))
          )}
        </nav>
      </aside>
      <RailResizer min={180} max={440} className="context-resizer" />
      <main className="workspace-canvas api-canvas">
        {!selected ? (
          <div className="empty-workspace">
            <Network />
            <strong>{zh ? "选择一个 API" : "Select an API"}</strong>
          </div>
        ) : (
          <form onSubmit={submit}>
            <header className="canvas-heading api-heading">
              <div>
                <small>POST /jobs/{selected.name}</small>
                <h1>{selected.name}</h1>
                <p>
                  {selected.description ||
                    (zh ? "无接口说明" : "No description")}
                </p>
              </div>
              <span>
                <CheckCircle2 />
                {zh ? "可调用" : "Available"}
              </span>
            </header>
            <section className="api-form-card">
              <header>
                <div>
                  <Braces />
                  <strong>{zh ? "请求参数" : "Request parameters"}</strong>
                </div>
                <small>
                  {Object.keys(selected.input_schema.properties || {}).length}{" "}
                  fields
                </small>
              </header>
              <div className="api-fields">
                {Object.entries(selected.input_schema.properties || {}).map(
                  ([name, schema]) => (
                    <SchemaField
                      key={name}
                      name={name}
                      schema={schema}
                      required={(selected.input_schema.required || []).includes(
                        name,
                      )}
                      value={values[name] ?? ""}
                      language={language}
                      variant="compact"
                      onChange={(value) =>
                        setValues((current) => ({ ...current, [name]: value }))
                      }
                    />
                  ),
                )}
              </div>
            </section>
            {error && <div className="inline-error">{error}</div>}
            <footer className="api-submit-row">
              <code>POST /jobs/{selected.name}</code>
              <button className="primary-button" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" /> : <Play />}
                {submitting
                  ? zh
                    ? "调用中"
                    : "Calling"
                  : zh
                    ? "调用 API"
                    : "Call API"}
              </button>
            </footer>
            {result !== undefined && (
              <section className="api-response">
                <header>
                  <span>
                    <i />
                    200
                  </span>
                  <strong>{zh ? "响应" : "Response"}</strong>
                </header>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </section>
            )}
          </form>
        )}
      </main>
    </section>
  );
}
