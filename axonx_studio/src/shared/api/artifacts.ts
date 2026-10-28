import { taskDirectory } from "../lib/tasks";
import { isRecord } from "../lib/values";
import type { RequestOptions } from "./client";
import type { ArtifactRecord, TaskMetadata } from "./contracts";
import { loadParquetRows, readJsonFile } from "./tables";

export function isArtifactRecord(value: unknown): value is ArtifactRecord {
  return (
    isRecord(value) &&
    typeof value.path === "string" &&
    !!value.path &&
    !value.path.startsWith("/") &&
    !value.path.includes("\\") &&
    !value.path.split("/").some((part) => ["..", ".", ""].includes(part)) &&
    typeof value.size === "number" &&
    Number.isInteger(value.size) &&
    value.size >= 0 &&
    typeof value.revision === "string" &&
    !!value.revision
  );
}

export function displayArtifacts(
  metadata: TaskMetadata,
): Record<string, ArtifactRecord> {
  const artifacts = (metadata.output_params.artifacts || {}) as Record<
    string,
    ArtifactRecord
  >;
  if (!metadata.replica) return artifacts;
  return Object.fromEntries(
    Object.entries(artifacts).flatMap(([name, artifact]) => {
      const actual = metadata.replica!.files[artifact.path];
      return actual
        ? [
            [
              name,
              { ...artifact, size: actual.size, revision: actual.revision },
            ],
          ]
        : [];
    }),
  );
}

export async function loadArtifactRows(
  taskId: string,
  artifact: ArtifactRecord,
  options: RequestOptions = {},
) {
  if (!isArtifactRecord(artifact)) throw new Error("Invalid artifact");
  return loadParquetRows(`${taskDirectory(taskId)}/${artifact.path}`, options);
}

export async function loadJsonArtifact(
  taskId: string,
  artifact: ArtifactRecord,
  options: RequestOptions = {},
): Promise<unknown> {
  if (!isArtifactRecord(artifact)) throw new Error("Invalid artifact");
  return readJsonFile(`${taskDirectory(taskId)}/${artifact.path}`, options);
}
