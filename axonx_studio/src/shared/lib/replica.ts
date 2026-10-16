import type { TaskMetadata } from "../api/contracts";
import type { ArtifactRecord } from "../api/contracts";
export type { ReplicaFile, DisplayReplica } from "../api/contracts";
export function displayArtifacts(metadata: TaskMetadata) {
  const artifacts = (metadata.output_params.artifacts || {}) as Record<
    string,
    ArtifactRecord
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
