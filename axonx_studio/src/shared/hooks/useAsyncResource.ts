import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, isAbortError } from "../lib/errors";

export function useAsyncResource<T>(
  loadResource: (signal: AbortSignal) => Promise<T>,
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const result = await loadResource(controller.signal);
      if (!controller.signal.aborted) setData(result);
      return result;
    } catch (reason) {
      if (!isAbortError(reason)) setError(errorMessage(reason));
      return null;
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [loadResource]);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  return { data, loading, error, reload: load };
}
