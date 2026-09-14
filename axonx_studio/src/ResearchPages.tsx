/* Dynamic artifact metadata is intentionally schema-flexible across task versions. */
/* eslint-disable @typescript-eslint/no-explicit-any, react-hooks/exhaustive-deps */
import { useEffect, useState } from "react";
import {
  AlertTriangle, ArrowRight, BarChart3, BrainCircuit, CalendarDays,
  CheckCircle2, Database, FileSpreadsheet, GitBranch, LoaderCircle,
  RefreshCw, Search, Sparkles, TrendingUp,
} from "lucide-react";
import { listWorkspaceEntries, previewWorkspaceFile } from "./api";
import type { Language, WorkspaceEntry, WorkspacePreview } from "./types";

type Meta = Record<string, any>;
type Row = Record<string, string>;
type Kind = "analysis" | "backtest" | "etl" | "training" | "predict";

const copy = {
  analysis: { zh: ["因子分析", "比较 IC、RankIC、分层收益与稳定性"], en: ["Factor analysis", "Compare IC, RankIC, quantile returns, and stability"] },
  backtest: { zh: ["回测分析", "收益曲线、绩效指标与每日持仓检查"], en: ["Backtest analytics", "Equity curves, performance metrics, and daily holdings"] },
  etl: { zh: ["ETL 数据集", "管理特征数据版本、覆盖范围与字段结构"], en: ["ETL datasets", "Manage feature dataset versions, coverage, and schema"] },
  training: { zh: ["模型管理", "追踪训练实验、验证效果与特征贡献"], en: ["Model registry", "Track experiments, validation quality, and feature contribution"] },
  predict: { zh: ["预测结果", "检查模型输出、样本覆盖及上游训练版本"], en: ["Predictions", "Inspect model outputs, coverage, and upstream training versions"] },
} as const;

const fmt = (value: unknown, digits = 2) => {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (Math.abs(number) >= 1_000_000) return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 }).format(number);
  return number.toLocaleString("zh-CN", { maximumFractionDigits: digits });
};
const pct = (value: unknown) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : "—";
const bytes = (value: unknown) => {
  const n = Number(value); if (!Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"]; let size = n; let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[unit]}`;
};
const rowsOf = (preview?: WorkspacePreview | null): Row[] => {
  if (preview?.kind !== "csv") return [];
  return (preview.rows || []).map((row) => Object.fromEntries((preview.columns || []).map((column, index) => [column, row[index] || ""])));
};

async function readAllCsv(path: string, remoteIp?: string) {
  const rows: string[][] = []; let columns: string[] = [];
  for (let offset = 0; offset < 5000; offset += 200) {
    const page = await previewWorkspaceFile(path, offset, 200, remoteIp);
    columns = page.columns || columns; rows.push(...(page.rows || []));
    if (!page.has_more) break;
  }
  return rows.map((row) => Object.fromEntries(columns.map((column, index) => [column, row[index] || ""])));
}

function useTasks(kind: Kind, remoteIp?: string, onConnection?: (online: boolean) => void) {
  const [tasks, setTasks] = useState<Meta[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const load = () => {
    setLoading(true); setError("");
    listWorkspaceEntries(kind, remoteIp).then(async (directory) => {
      const dirs = directory.entries.filter((entry) => entry.kind === "directory");
      const values: Meta[] = await Promise.all(dirs.map(async (entry): Promise<Meta> => {
        try { const preview = await previewWorkspaceFile(`${entry.path}/metadata.json`, 0, 200, remoteIp); return { ...(preview.data as Meta), _path: entry.path, _modified: entry.modified_at }; }
        catch { return { task_id: entry.name, task_type: kind, _path: entry.path, _modified: entry.modified_at }; }
      }));
      setTasks(values.sort((a, b) => String(b.created_at || b._modified).localeCompare(String(a.created_at || a._modified)))); onConnection?.(true);
    }).catch((reason) => { setError(reason instanceof Error ? reason.message : String(reason)); onConnection?.(false); }).finally(() => setLoading(false));
  };
  useEffect(load, [kind, remoteIp]);
  return { tasks, loading, error, load };
}

export function ResearchPage({ kind, language, remoteIp, onConnection, onNavigate }: {
  kind: Kind; language: Language; remoteIp?: string; onConnection: (online: boolean) => void; onNavigate: (page: any) => void;
}) {
  const zh = language === "zh"; const labels = copy[kind][language];
  const { tasks, loading, error, load } = useTasks(kind, remoteIp, onConnection);
  const [selectedId, setSelectedId] = useState(""); const [query, setQuery] = useState("");
  useEffect(() => { if (tasks.length && !tasks.some((task) => task.task_id === selectedId)) setSelectedId(tasks[0].task_id); }, [tasks, selectedId]);
  const selected = tasks.find((task) => task.task_id === selectedId);
  const visible = tasks.filter((task) => `${task.task_id} ${task.task_name}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="workspace-page research-page">
    <div className="page-heading"><div><p className="eyebrow">RESEARCH / {kind.toUpperCase()}</p><h1>{labels[0]}</h1><span>{labels[1]}</span></div><button className="secondary-button" onClick={load}><RefreshCw className={loading ? "spin" : ""} />{zh ? "刷新" : "Refresh"}</button></div>
    {error && <div className="error-banner"><AlertTriangle /><div><strong>{zh ? "无法读取任务产物" : "Unable to load artifacts"}</strong><span>{error}</span></div></div>}
    <div className="research-layout">
      <aside className="run-index"><header><div><strong>{zh ? "任务版本" : "TASK VERSIONS"}</strong><span>{tasks.length}</span></div><label><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={zh ? "搜索 task_id" : "Search task_id"} /></label></header>
        <div>{loading && !tasks.length ? <span className="run-loading"><LoaderCircle className="spin" /></span> : visible.map((task) => <button key={task.task_id} className={selectedId === task.task_id ? "active" : ""} onClick={() => setSelectedId(task.task_id)}><i /><span><strong>{task.task_name || kind}</strong><code>{task.task_id}</code><small>{task.created_at ? new Date(task.created_at).toLocaleString(language === "zh" ? "zh-CN" : "en") : "metadata unavailable"}</small></span><ArrowRight /></button>)}</div>
      </aside>
      <main className="research-canvas">{selected ? <ArtifactDetail kind={kind} meta={selected} language={language} remoteIp={remoteIp} onNavigate={onNavigate} /> : !loading && <div className="empty-research"><Database /><strong>{zh ? `暂无 ${kind} 任务` : `No ${kind} tasks`}</strong><span>{zh ? "任务产出后会自动出现在这里。" : "Task artifacts will appear here automatically."}</span></div>}</main>
    </div>
  </section>;
}

function ArtifactDetail({ kind, meta, language, remoteIp, onNavigate }: { kind: Kind; meta: Meta; language: Language; remoteIp?: string; onNavigate: (page: any) => void }) {
  const zh = language === "zh"; const [csv, setCsv] = useState<Record<string, Row[]>>({}); const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true; setLoading(true); const artifacts = meta.artifacts || {};
    const wanted = kind === "analysis" ? ["result", "quantiles"] : kind === "backtest" ? ["daily", "overall"] : kind === "training" ? ["feature_importance", "evaluation_history"] : [];
    Promise.all(wanted.filter((key) => artifacts[key]).map(async (key) => [key, await readAllCsv(`${meta._path}/${artifacts[key]}`, remoteIp)] as const)).then((items) => alive && setCsv(Object.fromEntries(items))).finally(() => alive && setLoading(false));
    if (!wanted.length) setLoading(false); return () => { alive = false; };
  }, [meta.task_id, remoteIp, kind]);
  const upstream = kind === "analysis" ? meta.source?.etl_task_id : kind === "backtest" ? meta.source?.prediction_task_id : kind === "training" ? meta.source?.etl_task_id : kind === "predict" ? meta.source?.training_task_id : null;
  const upstreamPage = kind === "analysis" || kind === "training" ? "etl" : kind === "backtest" ? "predict" : kind === "predict" ? "training" : null;
  return <>{<header className="artifact-header"><div><span className={`artifact-kind ${kind}`}>{iconFor(kind)}</span><div><small>{meta.task_name || kind}</small><h2>{meta.task_id}</h2></div></div><span className="ready-badge"><CheckCircle2 />{zh ? "产物就绪" : "Artifacts ready"}</span></header>}
    {upstream && <div className="lineage-strip"><span><GitBranch />{zh ? "数据血缘" : "LINEAGE"}</span><button onClick={() => onNavigate(upstreamPage)}><em>{upstreamPage?.toUpperCase()}</em><code>{upstream}</code><ArrowRight /></button><i /><strong><em>{kind.toUpperCase()}</em><code>{meta.task_id}</code></strong></div>}
    {loading ? <div className="research-loading"><LoaderCircle className="spin" /></div> : kind === "analysis" ? <AnalysisView meta={meta} result={csv.result || []} quantiles={csv.quantiles || []} zh={zh} /> : kind === "backtest" ? <BacktestView meta={meta} daily={csv.daily || []} overall={csv.overall || []} zh={zh} remoteIp={remoteIp} /> : kind === "training" ? <TrainingView meta={meta} importance={csv.feature_importance || []} history={csv.evaluation_history || []} zh={zh} /> : kind === "etl" ? <EtlView meta={meta} zh={zh} /> : <PredictView meta={meta} zh={zh} />}
  </>;
}

const iconFor = (kind: Kind) => kind === "analysis" ? <Sparkles /> : kind === "backtest" ? <TrendingUp /> : kind === "training" ? <BrainCircuit /> : kind === "predict" ? <BarChart3 /> : <Database />;
function Kpis({ items }: { items: { label: string; value: React.ReactNode; hint?: string }[] }) { return <div className="artifact-kpis">{items.map((item) => <article key={item.label}><small>{item.label}</small><strong>{item.value}</strong>{item.hint && <span>{item.hint}</span>}</article>)}</div>; }

function AnalysisView({ meta, result, quantiles, zh }: { meta: Meta; result: Row[]; quantiles: Row[]; zh: boolean }) {
  const [label, setLabel] = useState("label_1d"); const filtered = result.filter((row) => row.label === label).sort((a, b) => Math.abs(Number(b.rankic_mean)) - Math.abs(Number(a.rankic_mean))); const top = filtered.slice(0, 100);
  const labels = Array.from(new Set(result.map((row) => row.label)));
  return <div className="artifact-content"><Kpis items={[{ label: zh ? "因子数" : "FACTORS", value: fmt(meta.feature_count, 0) }, { label: zh ? "分析样本" : "SAMPLES", value: fmt(meta.rows, 0) }, { label: zh ? "有效交易日" : "TRADING DAYS", value: fmt(filtered[0]?.valid_days, 0) }, { label: zh ? "分组数" : "QUANTILES", value: fmt(meta.config?.quantiles, 0) }]} />
    <section className="viz-card wide factor-ranking-bars"><header><div><small>FACTOR SIGNAL</small><h3>{zh ? "RankIC 绝对值 Top 100" : "Top 100 factors by absolute RankIC"}</h3></div><select value={label} onChange={(e) => setLabel(e.target.value)}>{labels.map((item) => <option key={item}>{item}</option>)}</select></header><BarList rows={top} name="factor" value="rankic_mean" /></section>
    <section className="viz-card"><header><div><small>QUANTILE RETURN</small><h3>{zh ? "最佳因子分层收益" : "Top factor quantile return"}</h3></div></header><BarList rows={quantiles.filter((row) => row.factor === top[0]?.factor && row.label === label)} name="quantile" value="mean_return" percent /></section>
    <section className="viz-card"><header><div><small>FACTOR TABLE</small><h3>{zh ? "因子排名 Top 100" : "Top 100 factor ranking"}</h3></div></header><MiniTable rows={top} columns={["factor", "rankic_mean", "rankicir", "coverage", "direction"]} /></section></div>;
}

function BacktestView({ meta, daily, overall, zh, remoteIp }: { meta: Meta; daily: Row[]; overall: Row[]; zh: boolean; remoteIp?: string }) {
  const portfolios = Array.from(new Set(Object.keys(daily[0] || {}).map((key) => key.match(/^top(\d+)_net_value$/)?.[1]).filter(Boolean))) as string[];
  const [topN, setTopN] = useState(portfolios.includes("30") ? "30" : portfolios[0] || "");
  const [dayIndex, setDayIndex] = useState(Math.max(0, daily.length - 1)); const [holdings, setHoldings] = useState<Row[]>([]); const [holdingsLoading, setHoldingsLoading] = useState(false);
  useEffect(() => { setDayIndex(Math.max(0, daily.length - 1)); }, [meta.task_id, daily.length]);
  useEffect(() => {
    const file = meta.artifacts?.holdings; if (!file || !daily.length) { setHoldings([]); return; }
    const top = Number(meta.config?.holdings_top_n || 50); setHoldingsLoading(true);
    previewWorkspaceFile(`${meta._path}/${file}`, dayIndex * top, top, remoteIp).then((preview) => setHoldings(rowsOf(preview))).finally(() => setHoldingsLoading(false));
  }, [meta.task_id, meta._path, meta.artifacts?.holdings, dayIndex, daily.length, remoteIp]);
  const metric = (name: string, portfolio = `top${topN}`) => overall.find((row) => row.metric === name && row.portfolio === portfolio && row.benchmark === "none")?.value;
  return <div className="artifact-content"><Kpis items={[{ label: zh ? "累计收益" : "TOTAL RETURN", value: pct(Number(daily.at(-1)?.[`top${topN}_net_value`] || 1) - 1) }, { label: zh ? "年化收益" : "ANNUAL RETURN", value: pct(metric("annualized_net_return")) }, { label: "SHARPE", value: fmt(metric("sharpe")) }, { label: zh ? "最大回撤" : "MAX DRAWDOWN", value: pct(metric("max_drawdown")) }]} />
    <section className="viz-card wide equity-card"><header><div><small>EQUITY CURVE · {meta.date_range?.start}—{meta.date_range?.end}</small><h3>{zh ? "策略净值曲线" : "Portfolio equity curve"}</h3></div><select value={topN} onChange={(e) => setTopN(e.target.value)}>{portfolios.map((n) => <option key={n} value={n}>Top {n}</option>)}</select></header><LineChart rows={daily} value={`top${topN}_net_value`} benchmark="benchmark_hs300" /></section>
    <section className="viz-card"><header><div><small>PERFORMANCE</small><h3>{zh ? "核心指标" : "Core metrics"}</h3></div></header><MiniTable rows={overall.filter((row) => row.portfolio === `top${topN}`).slice(0, 12)} columns={["metric", "value"]} /></section>
    <section className="viz-card holdings-card"><header><div><small>DAILY HOLDINGS</small><h3>{zh ? "每日 Top50" : "Daily Top 50"}</h3></div>{daily.length > 0 && <time>{daily[dayIndex]?.trade_date}</time>}</header>{meta.artifacts?.holdings ? <><label className="date-scrubber"><span>{daily[0]?.trade_date}</span><input type="range" min="0" max={Math.max(0, daily.length - 1)} value={dayIndex} onChange={(e) => setDayIndex(Number(e.target.value))} /><span>{daily.at(-1)?.trade_date}</span></label>{holdingsLoading ? <div className="holdings-loading"><LoaderCircle className="spin" /></div> : <MiniTable rows={holdings} columns={["rank", "ts_code", "prediction", "weight", "daily_return"]} />}</> : <div className="data-gap"><AlertTriangle /><strong>{zh ? "旧任务未包含持仓明细" : "This older run has no holdings detail"}</strong><span>{zh ? "重新运行 backtest 后将生成 holdings.csv，并在这里按曲线日期展示 Top50。" : "Rerun the backtest to generate holdings.csv and inspect the Top 50 for any chart date here."}</span></div>}</section></div>;
}

function TrainingView({ meta, importance, history, zh }: { meta: Meta; importance: Row[]; history: Row[]; zh: boolean }) {
  const top = [...importance].sort((a, b) => Number(b.importance_gain) - Number(a.importance_gain)).slice(0, 12);
  return <div className="artifact-content"><Kpis items={[{ label: zh ? "算法" : "ALGORITHM", value: meta.model?.library || "—", hint: meta.model?.library_version }, { label: zh ? "最佳迭代" : "BEST ITERATION", value: fmt(meta.model?.best_iteration, 0) }, { label: "VALIDATION IC", value: fmt(meta.validation_metrics?.ic_mean, 4) }, { label: "RANK IC", value: fmt(meta.validation_metrics?.rankic_mean, 4) }]} />
    <section className="viz-card wide"><header><div><small>LEARNING CURVE</small><h3>{zh ? "验证集损失" : "Validation loss"}</h3></div></header><LineChart rows={history} value="validation_l2" /></section><section className="viz-card"><header><div><small>FEATURE IMPORTANCE</small><h3>{zh ? "特征贡献 Top 12" : "Top 12 feature contribution"}</h3></div></header><BarList rows={top} name="feature" value="importance_gain" /></section><section className="viz-card"><header><div><small>MODEL ARTIFACT</small><h3>{zh ? "模型版本" : "Model version"}</h3></div></header><ArtifactFiles meta={meta} /></section></div>;
}

function EtlView({ meta, zh }: { meta: Meta; zh: boolean }) { const features = meta.feature_columns || []; return <div className="artifact-content"><Kpis items={[{ label: zh ? "数据行数" : "ROWS", value: fmt(meta.rows, 0) }, { label: zh ? "股票数" : "SYMBOLS", value: fmt(meta.symbols, 0) }, { label: zh ? "特征数" : "FEATURES", value: fmt(features.length, 0) }, { label: zh ? "数据范围" : "DATE RANGE", value: `${meta.date_range?.start || "—"} — ${meta.date_range?.end || "—"}` }]} /><section className="viz-card wide"><header><div><small>FEATURE SCHEMA</small><h3>{zh ? "Alpha158 特征空间" : "Alpha158 feature space"}</h3></div></header><div className="feature-cloud">{features.map((feature: string) => <code key={feature}>{feature.replace("f_alpha158_", "")}</code>)}</div></section><section className="viz-card"><header><div><small>LABELS</small><h3>{zh ? "监督目标" : "Learning targets"}</h3></div></header><div className="label-groups">{Object.entries(meta.labels || {}).filter(([, value]) => Array.isArray(value)).map(([key, value]) => <div key={key}><strong>{key}</strong><span>{(value as string[]).join(" · ")}</span></div>)}</div></section><section className="viz-card"><header><div><small>ARTIFACTS</small><h3>{zh ? "数据文件" : "Dataset files"}</h3></div></header><ArtifactFiles meta={meta} /></section></div>; }
function PredictView({ meta, zh }: { meta: Meta; zh: boolean }) { return <div className="artifact-content"><Kpis items={[{ label: zh ? "预测行数" : "PREDICTIONS", value: fmt(meta.rows, 0) }, { label: zh ? "目标" : "TARGET", value: meta.model_target }, { label: zh ? "开始日期" : "START", value: meta.date_range?.start }, { label: zh ? "结束日期" : "END", value: meta.date_range?.end }]} /><section className="viz-card wide prediction-overview"><div><BarChart3 /><h3>{zh ? "截面预测数据已就绪" : "Cross-sectional predictions ready"}</h3><p>{zh ? "预测产物以 Parquet 保存，包含每日全市场评分、真实收益和指数权重，可继续用于回测。" : "The Parquet artifact contains daily market-wide scores, realized returns, and index weights for downstream backtests."}</p></div><ArtifactFiles meta={meta} /></section></div>; }

function ArtifactFiles({ meta }: { meta: Meta }) { return <div className="artifact-files">{Object.entries(meta.artifact_integrity || {}).map(([name, file]: [string, any]) => <div key={name}><FileSpreadsheet /><span><strong>{name}</strong><code>{file.path}</code></span><em>{bytes(file.bytes)}</em></div>)}</div>; }
function MiniTable({ rows, columns }: { rows: Row[]; columns: string[] }) { return <div className="mini-table"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{Number.isFinite(Number(row[column])) && row[column] !== "" ? fmt(row[column], 4) : row[column]}</td>)}</tr>)}</tbody></table></div>; }
function BarList({ rows, name, value, percent = false }: { rows: Row[]; name: string; value: string; percent?: boolean }) { const max = Math.max(...rows.map((row) => Math.abs(Number(row[value]))), 0.000001); return <div className="bar-list">{rows.map((row, index) => <div key={`${row[name]}-${index}`}><code>{row[name]}</code><span><i className={Number(row[value]) < 0 ? "negative" : ""} style={{ width: `${Math.max(2, Math.abs(Number(row[value])) / max * 100)}%` }} /></span><strong>{percent ? pct(row[value]) : fmt(row[value], 4)}</strong></div>)}</div>; }
function LineChart({ rows, value, benchmark }: { rows: Row[]; value: string; benchmark?: string }) {
  const series = rows.map((row) => Number(row[value])).filter(Number.isFinite); const bench = benchmark ? rows.map((row) => Number(row[benchmark])).filter(Number.isFinite) : [];
  const all = [...series, ...bench]; if (!all.length) return <div className="chart-empty">NO SERIES DATA</div>;
  const min = Math.min(...all), max = Math.max(...all), range = max - min || 1; const point = (v: number, i: number, length: number) => `${20 + i / Math.max(1, length - 1) * 760},${220 - (v - min) / range * 190}`;
  const path = (values: number[]) => values.map((v, i) => `${i ? "L" : "M"}${point(v, i, values.length)}`).join(" ");
  return <div className="line-chart"><svg viewBox="0 0 800 250" preserveAspectRatio="none"><line x1="20" y1="220" x2="780" y2="220" className="chart-axis" />{bench.length > 0 && <path d={path(bench)} className="chart-benchmark" />}<path d={path(series)} className="chart-primary" /></svg><footer><span>{rows[0]?.trade_date || rows[0]?.iteration}</span><strong>{fmt(series.at(-1), 4)}</strong><span>{rows.at(-1)?.trade_date || rows.at(-1)?.iteration}</span></footer></div>;
}

export function TusharePage({ language, remoteIp, onConnection }: { language: Language; remoteIp?: string; onConnection: (online: boolean) => void }) {
  const zh = language === "zh"; const [years, setYears] = useState<WorkspaceEntry[]>([]); const [year, setYear] = useState(""); const [days, setDays] = useState<WorkspaceEntry[]>([]); const [loading, setLoading] = useState(true);
  const load = () => { setLoading(true); listWorkspaceEntries("tushare", remoteIp).then((result) => { const values = result.entries.filter((entry) => entry.kind === "directory").reverse(); setYears(values); setYear((current) => current || values[0]?.name || ""); onConnection(true); }).catch(() => onConnection(false)).finally(() => setLoading(false)); };
  useEffect(load, [remoteIp]); useEffect(() => { if (!year) return; listWorkspaceEntries(`tushare/${year}`, remoteIp).then((result) => setDays(result.entries.filter((entry) => entry.kind === "directory").reverse())); }, [year, remoteIp]);
  return <section className="workspace-page research-page"><div className="page-heading"><div><p className="eyebrow">DATA / TUSHARE API</p><h1>{zh ? "Tushare 数据" : "Tushare data"}</h1><span>{zh ? "按交易日检查 API 落盘覆盖与数据接口。" : "Inspect API landing coverage and datasets by trading day."}</span></div><button className="secondary-button" onClick={load}><RefreshCw className={loading ? "spin" : ""} />{zh ? "刷新" : "Refresh"}</button></div><Kpis items={[{ label: zh ? "覆盖年份" : "YEARS", value: years.length }, { label: zh ? "最早年份" : "EARLIEST", value: years.at(-1)?.name }, { label: zh ? "最新年份" : "LATEST", value: years[0]?.name }, { label: zh ? "选中年度交易日" : "TRADING DAYS", value: days.length }]} /><div className="tushare-layout"><aside className="year-rail">{years.map((item) => <button key={item.path} className={year === item.name ? "active" : ""} onClick={() => setYear(item.name)}><CalendarDays /><strong>{item.name}</strong><ArrowRight /></button>)}</aside><section className="api-calendar"><header><div><small>TUSHARE / {year}</small><h2>{zh ? "交易日数据落盘" : "Daily API snapshots"}</h2></div><span>{days.length} DAYS</span></header><div>{days.map((day) => <article key={day.path}><time>{day.name}</time><span><i>daily</i><i>adj_factor</i><i className="optional">index_weight · monthly</i></span><CheckCircle2 /></article>)}</div></section></div></section>;
}
