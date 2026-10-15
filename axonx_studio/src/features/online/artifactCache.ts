import type { ArtifactRecord } from "../../shared/api/contracts";
import { loadArtifactRows } from "./api";

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

  async load(artifact: ArtifactRecord, signal?: AbortSignal): Promise<Rows> {
    signal?.throwIfAborted();
    const key = JSON.stringify([
      this.target,
      this.taskId,
      artifact.path,
      artifact.sha256,
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
      request = loadArtifactRows(
        this.taskId,
        artifact,
        this.target,
        controller.signal,
      )
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

  clear(): void {
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    this.pending.clear();
    this.entries.clear();
    this.bytes = 0;
  }
}
