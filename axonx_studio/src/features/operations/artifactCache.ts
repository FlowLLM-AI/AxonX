import { loadArtifactRows } from "../../shared/api/artifacts";
import type { ArtifactRecord } from "../../shared/api/contracts";
import { restorePortfolioSignals } from "../research/portfolio";
import { activeCommits, type OnlineCommit, type OnlineHistory } from "./report";

type Rows = Record<string, unknown>[];

/** One report owns this bounded cache and every request it starts. */
export class ArtifactTableCache {
  private readonly entries = new Map<string, { rows: Rows; bytes: number }>();
  private readonly pending = new Map<string, Promise<Rows>>();
  private readonly controllers = new Set<AbortController>();
  private bytes = 0;

  constructor(
    private readonly taskId: string,
    private readonly target?: string,
    private readonly maxBytes = 16 * 1024 * 1024,
  ) {}

  async load(
    artifact: ArtifactRecord,
    signal?: AbortSignal,
    taskId = this.taskId,
  ): Promise<Rows> {
    signal?.throwIfAborted();
    const key = JSON.stringify([
      this.target,
      taskId,
      artifact.path,
      artifact.revision,
    ]);
    const cached = this.entries.get(key);
    if (cached) {
      this.entries.delete(key);
      this.entries.set(key, cached);
      return cached.rows;
    }
    let request = this.pending.get(key);
    if (!request) {
      const controller = new AbortController();
      this.controllers.add(controller);
      request = loadArtifactRows(taskId, artifact, {
        target: this.target,
        signal: controller.signal,
      })
        .then((rows) => {
          controller.signal.throwIfAborted();
          // A conservative serialized-size budget bounds retained table data.
          const bytes = JSON.stringify(rows).length * 2;
          if (bytes <= this.maxBytes) {
            this.entries.set(key, { rows, bytes });
            this.bytes += bytes;
            while (this.bytes > this.maxBytes || this.entries.size > 32) {
              const oldest = this.entries.keys().next().value!;
              this.bytes -= this.entries.get(oldest)!.bytes;
              this.entries.delete(oldest);
            }
          }
          return rows;
        })
        .finally(() => {
          this.controllers.delete(controller);
          if (this.pending.get(key) === request) this.pending.delete(key);
        });
      this.pending.set(key, request);
    }
    // Tab cancellation detaches the caller; the report still owns the shared request.
    const rows = await request;
    signal?.throwIfAborted();
    return rows;
  }

  async signals(commit: OnlineCommit, signal?: AbortSignal): Promise<Rows> {
    const read = (role: string) =>
      this.load(commit.artifacts[role], signal, commit.task_id);
    const [predictions, rankings, scores] = await Promise.all([
      read("predictions"),
      read("rankings"),
      commit.artifacts.scores ? read("scores") : Promise.resolve(null),
    ]);
    return restorePortfolioSignals(
      predictions,
      rankings,
      commit.protocol.report.score_column,
      scores,
    );
  }

  async ledger(
    commit: OnlineCommit,
    history: OnlineHistory | null | undefined,
    role: string,
    signal?: AbortSignal,
  ) {
    const index = history?.commits.findIndex(
      (c) => c.commit_id === commit.commit_id,
    );
    if (index !== undefined && index < 0)
      throw new Error("Selected publication is missing from its history");
    const commits =
      history && ["daily", "trades"].includes(role)
        ? activeCommits({
            ...history,
            commits: history.commits.slice(0, index! + 1),
          })
        : [commit];
    return (
      await Promise.all(
        commits.map(async (c) => {
          const rows = await this.load(c.artifacts[role], signal, c.task_id);
          if (
            rows.some(
              (row) =>
                !Object.hasOwn(
                  c.protocol.report.portfolios,
                  String(row.portfolio_key),
                ) ||
                (role !== "summary" &&
                  row[role === "trades" ? "exit_date" : "trade_date"] !==
                    c.trade_date),
            )
          ) {
            throw new Error("Ledger rows differ from their daily publication");
          }
          return rows;
        }),
      )
    ).flat();
  }

  clear(): void {
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    this.pending.clear();
    this.entries.clear();
    this.bytes = 0;
  }
}
