import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Braces, CheckCircle2, LoaderCircle, Network, Play, Search } from "lucide-react";
import { invokeApi, listJobs } from "./api";
import { RailResizer } from "./RailResizer";
import type { ContextOption, JobInfo, JsonSchema, Language, MachineNode } from "./types";

type FormValues = Record<string, string | boolean>;

export function ApiWorkspace({ language, machine, initialName, onSelected, onOptionsChange, onConnection }: {
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
  const [values, setValues] = useState<FormValues>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<unknown>();

  const load = useCallback(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    listJobs(machine.isLocal ? undefined : machine.address, controller.signal).then((items) => {
      setApis(items);
      setSelectedName((current) => items.some((item) => item.name === current) ? current : "");
      onConnection(true);
    }).catch((reason) => { if (reason?.name !== "AbortError") { setError(String(reason)); onConnection(false); } }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [machine.address, machine.isLocal, onConnection]);
  useEffect(load, [load]);
  useEffect(() => { if (initialName && apis.some((item) => item.name === initialName)) setSelectedName(initialName); }, [initialName, apis]);
  useEffect(() => { onOptionsChange?.(apis.map((api) => ({ value: api.name, label: api.name, detail: "POST" }))); }, [apis, onOptionsChange]);

  const selected = apis.find((item) => item.name === selectedName);
  const visible = useMemo(() => apis.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase())), [apis, query]);
  useEffect(() => {
    if (!selected) return;
    const next: FormValues = {};
    for (const [name, schema] of Object.entries(selected.inputSchema.properties || {})) next[name] = schema.type === "boolean" ? Boolean(schema.default) : schema.default == null ? "" : typeof schema.default === "object" ? JSON.stringify(schema.default, null, 2) : String(schema.default);
    setValues(next); setResult(undefined); setError("");
  }, [selected]);

  const choose = (name: string) => { setSelectedName(name); onSelected(name); };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!selected) return;
    const body: Record<string, unknown> = {};
    try {
      for (const [name, schema] of Object.entries(selected.inputSchema.properties || {})) {
        const value = values[name]; if (value === "" || value === undefined) continue;
        body[name] = parseValue(value, schema);
      }
      setSubmitting(true); setError(""); setResult(await invokeApi(selected.name, body, machine.isLocal ? undefined : machine.address)); onConnection(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    finally { setSubmitting(false); }
  };

  return <section className="api-workspace unified-workspace">
    <aside className="context-rail api-index">
      <header><small>PUBLIC API</small><strong>{zh ? "接口" : "Interfaces"}</strong><em>{apis.length}</em></header>
      <label className="context-search"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索 API" : "Search APIs"} /></label>
      <nav>{loading && !apis.length ? <LoaderCircle className="spin context-loader" /> : visible.map((api) => <button key={api.name} className={selectedName === api.name ? "active" : ""} onClick={() => choose(api.name)}><Network /><span><strong>{api.name}</strong><small>POST /jobs/{api.name}</small></span><ArrowRight /></button>)}</nav>
    </aside>
    <RailResizer min={240} max={440} className="context-resizer" />
    <main className="workspace-canvas api-canvas">
      {!selected ? <div className="empty-workspace"><Network /><strong>{zh ? "选择一个 API" : "Select an API"}</strong></div> : <form onSubmit={submit}>
        <header className="canvas-heading api-heading"><div><small>POST /jobs/{selected.name}</small><h1>{selected.name}</h1><p>{selected.description || (zh ? "无接口说明" : "No description")}</p></div><span><CheckCircle2 />{zh ? "可调用" : "Available"}</span></header>
        <section className="api-form-card"><header><div><Braces /><strong>{zh ? "请求参数" : "Request parameters"}</strong></div><small>{Object.keys(selected.inputSchema.properties || {}).length} fields</small></header><div className="api-fields">{Object.entries(selected.inputSchema.properties || {}).map(([name, schema]) => <ApiField key={name} name={name} schema={schema} required={(selected.inputSchema.required || []).includes(name)} value={values[name]} onChange={(value) => setValues((current) => ({ ...current, [name]: value }))} zh={zh} />)}</div></section>
        {error && <div className="inline-error">{error}</div>}
        <footer className="api-submit-row"><code>POST /jobs/{selected.name}</code><button className="primary-button" disabled={submitting}>{submitting ? <LoaderCircle className="spin" /> : <Play />}{submitting ? (zh ? "调用中" : "Calling") : (zh ? "调用 API" : "Call API")}</button></footer>
        {result !== undefined && <section className="api-response"><header><span><i />200</span><strong>{zh ? "响应" : "Response"}</strong></header><pre>{JSON.stringify(result, null, 2)}</pre></section>}
      </form>}
    </main>
  </section>;
}

function ApiField({ name, schema, required, value, onChange, zh }: { name: string; schema: JsonSchema; required: boolean; value: string | boolean | undefined; onChange: (value: string | boolean) => void; zh: boolean }) {
  const type = Array.isArray(schema.type) ? schema.type.find((item) => item !== "null") : schema.type;
  return <label className={type === "object" || type === "array" ? "wide" : ""}><span><strong>{schema.title || name}</strong><em>{required ? (zh ? "必填" : "Required") : (zh ? "选填" : "Optional")}</em></span>{schema.description && <small>{schema.description}</small>}{schema.enum ? <select value={String(value || "")} required={required} onChange={(event) => onChange(event.target.value)}><option value="">—</option>{schema.enum.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select> : type === "boolean" ? <button type="button" className={`switch-control ${value ? "on" : ""}`} onClick={() => onChange(!value)}><i /><span>{value ? "True" : "False"}</span></button> : type === "object" || type === "array" ? <textarea value={String(value || "")} required={required} placeholder={type === "array" ? "[]" : "{}"} onChange={(event) => onChange(event.target.value)} /> : <input type={type === "integer" || type === "number" ? "number" : "text"} step={type === "integer" ? 1 : type === "number" ? "any" : undefined} value={String(value || "")} required={required} onChange={(event) => onChange(event.target.value)} />}</label>;
}

function parseValue(value: string | boolean, schema: JsonSchema): unknown {
  if (typeof value === "boolean") return value;
  if (schema.enum) return schema.enum.find((item) => String(item) === value) ?? value;
  const type = Array.isArray(schema.type) ? schema.type.find((item) => item !== "null") : schema.type;
  if (type === "integer") return Number.parseInt(value, 10);
  if (type === "number") return Number(value);
  if (type === "object" || type === "array") return JSON.parse(value);
  if (type === "boolean") return value === "true";
  return value;
}
