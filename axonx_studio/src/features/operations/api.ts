import type { RequestOptions } from "../../shared/api/client";
import { readJsonFile } from "../../shared/api/tables";
import { taskDirectory } from "../../shared/lib/tasks";
import { isRecord } from "../../shared/lib/values";
import { parseHistory, parseStockReport, type OnlineCommit } from "./report";
import { parseQuality } from "./report";

function dailyReport(value: unknown, taskId: string, modelId?: string) {
  if (!isRecord(value) || !isRecord(value.output_params))
    throw new Error("Invalid Task metadata");
  const output = value.output_params;
  let raw = output.report;
  if (isRecord(output.models)) {
    const [slot, name] = (modelId || "").split(":");
    const models = output.models[slot];
    raw =
      isRecord(models) && isRecord(models[name]) ? models[name].report : null;
  }
  if (!raw) return null;
  const report = parseStockReport(raw);
  if (
    report.commit.task_id !== taskId ||
    Date.parse(report.commit.started_at) !==
      Date.parse(String(value.started_at))
  )
    throw new Error("Online result differs from its producing Task execution");
  return report;
}

export async function loadHistory(
  taskId: string,
  options: RequestOptions = {},
  allowMissing = false,
  modelId?: string,
  reads = new Map<string, Promise<unknown>>(),
) {
  const read = (id: string, optional = false) => {
    const key = `${id}:${optional}`;
    if (!reads.has(key))
      reads.set(
        key,
        readJsonFile(`${taskDirectory(id)}/metadata.json`, options, optional),
      );
    return reads.get(key)!;
  };
  const value = await read(taskId, allowMissing);
  if (allowMissing && value === undefined) return null;
  const report = dailyReport(value, taskId, modelId);
  if (!report) {
    if (allowMissing) return null;
    throw new Error("Missing daily online result");
  }
  const input =
    isRecord(value) && isRecord(value.input_params) ? value.input_params : {};
  const archiveModel =
    modelId ||
    `${report.commit.trade_time}:${input.model_task_name || input.task_name || ""}`;
  const sources = report.commit.protocol.history_sources || [];
  if (!Array.isArray(sources)) throw new Error("Invalid daily history sources");
  const previous = await Promise.all(
    sources.map(async (source) => {
      if (
        !isRecord(source) ||
        typeof source.task_id !== "string" ||
        typeof source.started_at !== "string" ||
        typeof source.commit_id !== "string"
      )
        throw new Error("Invalid daily history source");
      const archived = dailyReport(
        await read(source.task_id),
        source.task_id,
        archiveModel,
      )?.commit;
      if (
        !archived ||
        archived.commit_id !== source.commit_id ||
        Date.parse(archived.started_at) !== Date.parse(source.started_at) ||
        archived.trade_time !== report.commit.trade_time ||
        archived.trade_date >= report.commit.trade_date
      )
        throw new Error("Daily history source changed");
      return archived;
    }),
  );
  return parseHistory({
    version: 1,
    task_type: "inference",
    kind: "online_history",
    strategy_identity: report.commit.protocol.report.strategy_identity,
    commits: [...previous, report.commit],
  });
}
export async function loadQuality(commit: OnlineCommit) {
  return commit.protocol.quality ? parseQuality(commit.protocol.quality) : null;
}
