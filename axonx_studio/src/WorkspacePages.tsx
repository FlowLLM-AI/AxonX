import { useEffect, useMemo, useState } from "react";
import {
  Activity, ArrowRight, Blocks, Box, BrainCircuit, CheckCircle2,
  CircleDashed, Cpu, Database, FileCode2, LoaderCircle,
  Network, PackageOpen, RefreshCw, Search, Send, Sparkles, Workflow,
} from "lucide-react";
import { listInstalledTaskInfos, listJobs, listPlugins } from "./api";
import { t } from "./i18n";
import type { JobInfo, Language, MachineNode, PageId, PluginInfo, TaskInfo } from "./types";

export function HomePage({ language, onNavigate }: {
  language: Language; onNavigate: (page: PageId) => void;
}) {
  const zh = language === "zh";
  return <section className="workspace-page overview-page">
    <div className="overview-hero">
      <div className="hero-copy"><p className="eyebrow">AXONX · QUANT</p><h1>{zh ? "量化 Harness 框架" : "A harness for quantitative workflows"}</h1><p>{zh ? "组织数据、研究、训练、预测与回测，并交给隔离的 Task Runtime 执行。" : "Organize data, research, training, prediction, and backtesting through isolated Task runtimes."}</p><div className="hero-actions"><button className="primary-button" onClick={() => onNavigate("submit")}><Send />{zh ? "提交Task" : "Submit Task"}<ArrowRight /></button><button className="secondary-button" onClick={() => onNavigate("tasks")}><Activity />{zh ? "查看运行" : "View runs"}</button></div></div>
    </div>
  </section>;
}

export function PluginsPage({ language, remoteIp, onConnection }: { language: Language; remoteIp?: string; onConnection: (online: boolean) => void }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const load = () => { setLoading(true); setError(""); listPlugins(remoteIp).then((result) => { setPlugins(result); onConnection(true); }).catch((reason) => { setError(String(reason)); onConnection(false); }).finally(() => setLoading(false)); };
  useEffect(load, [remoteIp, onConnection]);
  const zh = language === "zh";
  return <section className="workspace-page"><div className="page-heading"><div><p className="eyebrow">EXTENSIONS / PLUGINS</p><h1>{t(language).pages.plugins}</h1><span>{zh ? "查看当前机器安装的插件、版本与全部贡献能力。" : "Inspect installed plugins, versions, and contributions on this machine."}</span></div><button className="secondary-button" onClick={load}><RefreshCw className={loading ? "spin" : ""} />{t(language).refreshNow}</button></div>
    {error && <div className="error-banner"><CircleDashed /><div><strong>{zh ? "无法读取插件" : "Unable to load plugins"}</strong><span>{error}</span></div></div>}
    {loading && !plugins.length ? <div className="loading-state tall"><LoaderCircle className="spin" />{zh ? "正在读取插件…" : "Loading plugins…"}</div> : <div className="plugin-grid">{plugins.map((plugin) => <PluginCard key={`${plugin.distribution}-${plugin.version}`} plugin={plugin} language={language} />)}{!plugins.length && !loading && <div className="empty-surface"><PackageOpen /><h2>{zh ? "没有已安装插件" : "No installed plugins"}</h2><p>{zh ? "内置 Task 仍然可以正常使用。" : "Built-in Tasks remain available."}</p></div>}</div>}
  </section>;
}

function PluginCard({ plugin, language }: { plugin: PluginInfo; language: Language }) {
  const zh = language === "zh"; const components = Object.entries(plugin.components || {}).flatMap(([type, values]) => Object.keys(values).map((name) => `${type}:${name}`));
  return <article className="plugin-card"><header><span><PackageOpen /></span><div><small>{plugin.plugins?.join(" · ") || "AXONX PLUGIN"}</small><h2>{plugin.distribution}</h2></div><em>v{plugin.version}</em></header><div className="plugin-contributions"><Contribution icon={<Activity />} title="TASKS" values={Object.keys(plugin.tasks || {})} /><Contribution icon={<Workflow />} title="JOBS" values={Object.keys(plugin.jobs || {})} /><Contribution icon={<Blocks />} title="COMPONENTS" values={components} /></div><footer><span><CheckCircle2 />{zh ? "已安装" : "Installed"}</span><code>{plugin.wheel_sha256?.slice(0, 12) || "—"}</code></footer></article>;
}
function Contribution({ icon, title, values }: { icon: React.ReactNode; title: string; values: string[] }) { return <section><header>{icon}<span>{title}</span><b>{values.length}</b></header><div>{values.length ? values.map((value) => <code key={value}>{value}</code>) : <small>—</small>}</div></section>; }

export function JobCatalogPage({ language, machine, onConnection }: { language: Language; machine: MachineNode; onConnection: (online: boolean) => void }) {
  const [jobs, setJobs] = useState<JobInfo[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [query, setQuery] = useState("");
  const load = () => {
    const controller = new AbortController(); setLoading(true); setError("");
    listJobs(machine.isLocal ? undefined : machine.address, controller.signal).then((result) => { setJobs(result); onConnection(true); }).catch((reason) => {
      if (reason?.name !== "AbortError") { setError(reason instanceof Error ? reason.message : String(reason)); onConnection(false); }
    }).finally(() => setLoading(false));
    return () => controller.abort();
  };
  useEffect(load, [machine.id, machine.address, machine.isLocal, onConnection]);
  const filtered = useMemo(() => jobs.filter((job) => `${job.name} ${job.description}`.toLowerCase().includes(query.toLowerCase())), [jobs, query]); const zh = language === "zh";
  return <section className="workspace-page"><div className="page-heading"><div><p className="eyebrow">EXTENSIONS / JOB CATALOG</p><h1>{t(language).pages.jobs}</h1><span>{zh ? "由最新服务接口实时发现当前机器所有可公开调用的 Job。" : "Discover every publicly invocable Job from the selected machine."}</span></div><button className="secondary-button" onClick={() => load()}><RefreshCw className={loading ? "spin" : ""} />{t(language).refreshNow}</button></div>
    <div className="catalog-toolbar"><label className="catalog-filter"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索 Job 名称或描述" : "Search Job name or description"} /></label><span>{filtered.length} / {jobs.length} JOBS</span></div>
    {error && <div className="error-banner"><CircleDashed /><div><strong>{zh ? "无法读取 Job 目录" : "Unable to load Job catalog"}</strong><span>{error}</span></div></div>}
    {loading && !jobs.length ? <div className="loading-state tall"><LoaderCircle className="spin" />{zh ? "正在发现 Job…" : "Discovering Jobs…"}</div> : <div className="job-grid">{filtered.map((job) => <JobCard key={job.name} job={job} language={language} />)}{!filtered.length && !loading && <div className="empty-surface"><Network /><h2>{zh ? "没有匹配的 Job" : "No matching Jobs"}</h2></div>}</div>}
  </section>;
}

function JobCard({ job, language }: { job: JobInfo; language: Language }) {
  const zh = language === "zh"; const properties = Object.entries(job.inputSchema.properties || {}); const required = new Set(job.inputSchema.required || []); const remote = properties.some(([name]) => name === "remote_ip");
  return <article className="job-card"><header><span><Workflow /></span><div><small>PUBLIC JOB</small><h2>{job.name}</h2></div>{remote && <em>{zh ? "支持远程" : "REMOTE"}</em>}</header><p>{job.description || (zh ? "暂无描述" : "No description")}</p><section><div className="job-section-title"><span>{zh ? "输入参数" : "INPUT"}</span><b>{properties.length}</b></div><div className="job-fields">{properties.length ? properties.map(([name, schema]) => <div key={name}><code>{name}</code><span>{Array.isArray(schema.type) ? schema.type.join(" | ") : schema.type || "any"}</span>{required.has(name) && <i>{zh ? "必填" : "required"}</i>}</div>) : <small>{zh ? "无参数" : "No parameters"}</small>}</div></section><details><summary>{zh ? "查看完整接口 Schema" : "View full API schema"}</summary><pre>{JSON.stringify({ inputSchema: job.inputSchema, outputSchema: job.outputSchema }, null, 2)}</pre></details><footer><code>POST /jobs/{job.name}</code></footer></article>;
}

export function TaskCatalogPage({ language, remoteIp, onConnection, onSubmit }: { language: Language; remoteIp?: string; onConnection: (online: boolean) => void; onSubmit: () => void }) {
  const [tasks, setTasks] = useState<TaskInfo[]>([]); const [loading, setLoading] = useState(true); const [query, setQuery] = useState("");
  useEffect(() => { const controller = new AbortController(); setLoading(true); listInstalledTaskInfos(remoteIp, controller.signal).then((result) => { setTasks(result); onConnection(true); }).catch((reason) => { if (reason?.name !== "AbortError") onConnection(false); }).finally(() => setLoading(false)); return () => controller.abort(); }, [remoteIp, onConnection]);
  const filtered = useMemo(() => tasks.filter((task) => `${task.name} ${task.task_type} ${task.description}`.toLowerCase().includes(query.toLowerCase())), [tasks, query]); const zh = language === "zh";
  return <section className="workspace-page"><div className="page-heading"><div><p className="eyebrow">EXTENSIONS / TASK CATALOG</p><h1>{t(language).pages.taskCatalog}</h1><span>{zh ? "当前机器可执行的内置与插件 Task 定义。" : "Built-in and plugin Task definitions available on this machine."}</span></div><button className="primary-button" onClick={onSubmit}><Send />{t(language).pages.submit}</button></div><label className="catalog-filter"><Activity /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索名称、类型或描述" : "Search name, type, or description"} /></label><div className="definition-grid">{loading ? <div className="loading-state"><LoaderCircle className="spin" /></div> : filtered.map((task) => <article key={task.name}><header><span className={`catalog-icon type-${task.task_type}`}>{task.name[0].toUpperCase()}</span><div><small>{task.task_type}</small><h2>{task.name}</h2></div></header><p>{task.description}</p><footer><span>{Object.keys(task.config_schema.properties || {}).length} {zh ? "个参数" : "parameters"}</span><span>{task.output_keys.length} {zh ? "项输出" : "outputs"}</span></footer></article>)}</div></section>;
}

const pageDetails: Partial<Record<PageId, { zh: string; en: string; icon: React.ReactNode }>> = {
  datasets: { zh: "数据集目录、原始数据和特征数据需要新增数据资产 API。", en: "Dataset catalog, raw data, and feature data require a data asset API.", icon: <Database /> },
  factors: { zh: "RankIC、IC、分层收益和因子稳定性分析任务待开发。", en: "RankIC, IC, quantile returns, and stability analysis Tasks are planned.", icon: <Sparkles /> },
  training: { zh: "模型训练 Task 与实验记录能力待开发。", en: "Model training Tasks and experiment tracking are planned.", icon: <BrainCircuit /> },
  models: { zh: "模型版本、元数据与产物注册能力待开发。", en: "Model versions, metadata, and artifact registry are planned.", icon: <Box /> },
  inference: { zh: "批量推理与预测结果管理能力待开发。", en: "Batch inference and prediction result management are planned.", icon: <Cpu /> },
  strategies: { zh: "可复用策略定义与版本管理能力待开发。", en: "Reusable strategy definitions and versioning are planned.", icon: <Blocks /> },
  reports: { zh: "回测结果索引和 PDF 在线预览需要新增文件读取 API。", en: "Backtest indexing and PDF preview require a file read API.", icon: <FileCode2 /> },
  components: { zh: "插件贡献的 Component 已可获取；完整运行时目录 API 待开发。", en: "Plugin Components are available; a complete runtime catalog API is planned.", icon: <Blocks /> },
};

export function ComingSoonPage({ page, language, partial, detail }: { page: PageId; language: Language; partial?: boolean; detail?: string }) {
  const text = t(language); const info = pageDetails[page]; const zh = language === "zh";
  return <section className="workspace-page planned-page"><div className="planned-card"><div className="planned-icon">{info?.icon || <CircleDashed />}</div><span className={`development-badge ${partial ? "partial" : ""}`}>{partial ? (zh ? "部分可用" : "PARTIALLY AVAILABLE") : (zh ? "待开发" : "PLANNED")}</span><h1>{text.pages[page]}</h1><p>{detail || info?.[language] || text.comingHint}</p>{partial && <a href="#submit">{zh ? "前往提交任务" : "Go to Submit Task"}<ArrowRight /></a>}<div className="planned-rule"><i /><span>AXONX ROADMAP</span><i /></div></div></section>;
}
