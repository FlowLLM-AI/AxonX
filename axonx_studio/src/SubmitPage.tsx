import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Braces, Check, ChevronDown, ChevronRight, CircleDot, LoaderCircle, RefreshCw, Search, Send, Sparkles } from "lucide-react";
import { listInstalledTaskInfos, submitTask } from "./api";
import { interpolate, t } from "./i18n";
import type { JsonSchema, Language, TaskInfo } from "./types";

type FieldValue = string | boolean;

export function SubmitPage({ language, remoteIp, onViewTasks, onConnection }: { language: Language; remoteIp?: string; onViewTasks: () => void; onConnection: (online: boolean) => void }) {
  const text = t(language);
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [values, setValues] = useState<Record<string, FieldValue>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<TaskInfo["source"]>>(new Set());

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = await listInstalledTaskInfos(remoteIp);
      setTasks(result); setSelectedName((current) => current || result[0]?.name || ""); onConnection(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    finally { setLoading(false); }
  }, [onConnection, remoteIp]);

  useEffect(() => { void load(); }, [load]);
  const selected = tasks.find((task) => task.name === selectedName);
  const filtered = useMemo(() => tasks.filter((task) => `${task.name} ${task.task_type} ${task.description}`.toLowerCase().includes(search.toLowerCase())), [tasks, search]);
  const taskGroups = useMemo(() => [
    { source: "native" as const, label: text.nativeTasks, tasks: filtered.filter((task) => task.source !== "plugin") },
    { source: "plugin" as const, label: text.pluginTasks, tasks: filtered.filter((task) => task.source === "plugin") },
  ], [filtered, text.nativeTasks, text.pluginTasks]);

  useEffect(() => {
    if (!selected) return;
    const defaults: Record<string, FieldValue> = {};
    for (const [name, schema] of Object.entries(selected.config_schema.properties || {})) {
      if (schema.default !== undefined) defaults[name] = fieldText(schema.default, schema);
      else if (schemaType(schema) === "boolean") defaults[name] = false;
      else defaults[name] = "";
    }
    setValues(defaults); setFieldErrors({}); setSubmitted(false);
  }, [selectedName, selected]);

  const chooseTask = (name: string) => { setSelectedName(name); setSubmitted(false); };
  const toggleGroup = (source: TaskInfo["source"]) => setCollapsedGroups((current) => {
    const next = new Set(current);
    if (next.has(source)) next.delete(source);
    else next.add(source);
    return next;
  });
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!selected) return;
    const parsed: Record<string, unknown> = {}; const errors: Record<string, string> = {};
    const required = new Set(selected.config_schema.required || []);
    for (const [name, schema] of Object.entries(selected.config_schema.properties || {})) {
      const value = values[name]; const type = schemaType(schema);
      if (value === "" && required.has(name)) { errors[name] = text.required; continue; }
      if (value === "" || (type === "boolean" && value === false && schema.default === undefined && !required.has(name))) continue;
      try { parsed[name] = parseField(value, schema); }
      catch { errors[name] = text.jsonHint; }
    }
    setFieldErrors(errors); if (Object.keys(errors).length) return;
    setSubmitting(true); setError("");
    try { await submitTask(selected.name, parsed, remoteIp); setSubmitted(true); onConnection(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    finally { setSubmitting(false); }
  };

  return <section className="workspace-page submit-workspace">
    <div className="page-heading"><div><p className="eyebrow">TASK LAUNCHER / 02</p><h1>{text.submitTitle}</h1><span>{text.submitLead}</span></div></div>
    <div className="submit-layout">
      <aside className="catalog-panel">
        <header><div><p>{text.taskCatalog}</p><span>{interpolate(text.tasksAvailable, { count: tasks.length })}</span></div><button onClick={() => void load()} aria-label="Refresh"><RefreshCw className={loading ? "spin" : ""} /></button></header>
        <label className="catalog-search"><Search /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={text.findTask} /></label>
        <div className="task-catalog">
          {taskGroups.map((group) => {
            if (!group.tasks.length) return null;
            const expanded = !collapsedGroups.has(group.source) || Boolean(search.trim());
            const itemsId = `task-group-${group.source}`;
            return <section className={`task-catalog-group ${expanded ? "expanded" : "collapsed"}`} key={group.source}>
              <button type="button" className="catalog-group-toggle" aria-expanded={expanded} aria-controls={itemsId} onClick={() => toggleGroup(group.source)}><span><ChevronDown />{group.label}</span><small>{group.tasks.length}</small></button>
              {expanded && <div className="task-catalog-items" id={itemsId}>{group.tasks.map((task) => <button key={task.name} className={selectedName === task.name ? "active" : ""} onClick={() => chooseTask(task.name)}><span className={`catalog-icon type-${task.task_type}`}>{task.name.slice(0, 1).toUpperCase()}</span><div><strong>{task.name}</strong><small>{text.types[task.task_type] || task.task_type}</small></div><ChevronRight /></button>)}</div>}
            </section>;
          })}
          {!loading && !filtered.length && <div className="catalog-empty">{text.noInstalled}</div>}
        </div>
      </aside>
      <div className="form-panel">
        {loading && !selected && <div className="loading-state tall"><LoaderCircle className="spin" /> Loading Task catalog…</div>}
        {error && !selected && <div className="form-message error"><Braces /><h2>{text.catalogFailed}</h2><p>{error}</p><button className="secondary-button" onClick={() => void load()}>{text.retry}</button></div>}
        {selected && !submitted && <form onSubmit={(event) => void submit(event)}>
          <header className="task-form-header"><div className={`large-task-icon type-${selected.task_type}`}><Sparkles /></div><div><span className="type-label">{text.types[selected.task_type] || selected.task_type}</span><h2>{selected.name}</h2><p>{selected.description}</p></div></header>
          <section className="configuration-card">
            <div className="form-section-heading"><div><span className="section-heading-icon"><CircleDot /></span><span>{text.configure}</span></div><small>{Object.keys(selected.config_schema.properties || {}).length} fields</small></div>
            <div className="dynamic-form">{Object.entries(selected.config_schema.properties || {}).map(([name, schema]) => <SchemaField key={name} name={name} schema={schema} required={(selected.config_schema.required || []).includes(name)} value={values[name] ?? ""} error={fieldErrors[name]} language={language} onChange={(value) => setValues((current) => ({ ...current, [name]: value }))} />)}</div>
          </section>
          {!!selected.output_keys.length && <div className="output-preview"><span><Braces />{text.output}</span><div>{selected.output_keys.map((key) => <code key={key}>{key}</code>)}</div></div>}
          {error && <div className="inline-error">{error}</div>}
          <footer className="form-footer"><span>POST /jobs/submit</span><button className="primary-button submit-button" disabled={submitting}>{submitting ? <LoaderCircle className="spin" /> : <Send />} {submitting ? text.submitting : text.submit}<ArrowRight /></button></footer>
        </form>}
        {selected && submitted && <div className="success-state"><span className="success-rings"><i /><i /><Check /></span><p>SUBMITTED</p><h2>{text.submitted}</h2><span>{text.submittedHint}</span><code>{selected.name}</code><button className="primary-button" onClick={onViewTasks}>{text.viewTasks}<ArrowRight /></button><button className="link-button" onClick={() => setSubmitted(false)}>{language === "zh" ? "再提交一次" : "Submit another"}</button></div>}
      </div>
    </div>
  </section>;
}

function SchemaField({ name, schema, required, value, error, language, onChange }: { name: string; schema: JsonSchema; required: boolean; value: FieldValue; error?: string; language: Language; onChange: (value: FieldValue) => void }) {
  const text = t(language); const type = schemaType(schema); const id = `field-${name}`;
  return <label className={`schema-field ${type === "object" || type === "array" ? "wide" : ""}`} htmlFor={id}><div className="field-label"><span>{schema.title || humanize(name)}</span><em className={required ? "required" : ""}>{required ? text.required : text.optional}</em></div>{schema.description && <small>{schema.description}</small>}
    {schema.enum ? <select id={id} value={String(value)} onChange={(event) => onChange(event.target.value)} required={required}><option value="">{text.choose}</option>{schema.enum.map((item) => <option key={JSON.stringify(item)} value={JSON.stringify(item)}>{String(item)}</option>)}</select>
      : type === "boolean" ? <button id={id} type="button" className={`switch-control ${value ? "on" : ""}`} onClick={() => onChange(!value)} role="switch" aria-checked={Boolean(value)}><i /><span>{value ? "True" : "False"}</span></button>
      : type === "object" || type === "array" ? <textarea id={id} value={String(value)} onChange={(event) => onChange(event.target.value)} placeholder={type === "array" ? "[]" : "{}"} required={required} />
      : <input id={id} type={type === "integer" || type === "number" ? "number" : schema.format === "date" ? "date" : "text"} step={type === "integer" ? 1 : type === "number" ? "any" : undefined} min={schema.minimum} max={schema.maximum} value={String(value)} onChange={(event) => onChange(event.target.value)} required={required} />}
    {error && <span className="field-error">{error}</span>}</label>;
}

function schemaType(schema: JsonSchema): string { if (Array.isArray(schema.type)) return schema.type.find((type) => type !== "null") || "string"; if (schema.type) return schema.type; return schema.anyOf?.map(schemaType).find((type) => type !== "null") || "string"; }
function fieldText(value: unknown, schema: JsonSchema): FieldValue { if (schemaType(schema) === "boolean") return Boolean(value); if (schemaType(schema) === "object" || schemaType(schema) === "array") return JSON.stringify(value, null, 2); if (schema.enum) return JSON.stringify(value); return String(value ?? ""); }
function parseField(value: FieldValue, schema: JsonSchema): unknown { const type = schemaType(schema); if (schema.enum) return JSON.parse(String(value)); if (type === "boolean") return Boolean(value); if (type === "integer") return Number.parseInt(String(value), 10); if (type === "number") return Number(String(value)); if (type === "object" || type === "array") return JSON.parse(String(value)); return String(value); }
function humanize(value: string) { return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
