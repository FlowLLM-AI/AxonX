import { isRecord } from "../lib/values";
import type { ArtifactRecord } from "./contracts";
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
