export function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException
    ? reason.name === "AbortError"
    : typeof reason === "object" &&
        reason !== null &&
        "name" in reason &&
        reason.name === "AbortError";
}
