import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, isAbortError } from "../lib/errors";

export function useAsyncResource<T>(
  loadResource: (signal: AbortSignal) => Promise<T>,
) {
  const [state, setState] = useState<{
    resource: typeof loadResource;
    data: T | null;
    loading: boolean;
    error: string;
  }>({ resource: loadResource, data: null, loading: true, error: "" });
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((previous) => ({
      resource: loadResource,
      data: previous.resource === loadResource ? previous.data : null,
      loading: true,
      error: "",
    }));
    try {
      const data = await loadResource(controller.signal);
      if (!controller.signal.aborted)
        setState({ resource: loadResource, data, loading: false, error: "" });
      return data;
    } catch (reason) {
      if (!controller.signal.aborted && !isAbortError(reason))
        setState((previous) => ({
          ...previous,
          loading: false,
          error: errorMessage(reason),
        }));
      return null;
    } finally {
      if (!controller.signal.aborted)
        setState((previous) =>
          previous.loading ? { ...previous, loading: false } : previous,
        );
    }
  }, [loadResource]);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  // A new machine/selection must never briefly expose the previous resource.
  const current = state.resource === loadResource;
  return {
    data: current ? state.data : null,
    loading: !current || state.loading,
    error: current ? state.error : "",
    reload: load,
  };
}
