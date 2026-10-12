import type { TaskMetadata } from "../../features/tasks/types";
export interface ReplicaFile {
  size: number;
  sha256: string;
  sampled: boolean;
  rows: number | null;
  source_rows: number | null;
  dates: string[];
}
export interface DisplayReplica {
  purpose: "display";
  source_digest: string;
  policy_digest: string;
  files: Record<string, ReplicaFile>;
  omitted: Record<string, string>;
  source_log_path: string;
}
export function displayArtifacts(metadata: TaskMetadata) {
  const artifacts = (metadata.output_params.artifacts || {}) as Record<
    string,
    { path: string; size: number; sha256: string }
  >;
  if (!metadata.replica) return artifacts;
  return Object.fromEntries(
    Object.entries(artifacts).flatMap(([name, artifact]) => {
      const actual = metadata.replica!.files[artifact.path];
      return actual
        ? [[name, { ...artifact, size: actual.size, sha256: actual.sha256 }]]
        : [];
    }),
  );
}
