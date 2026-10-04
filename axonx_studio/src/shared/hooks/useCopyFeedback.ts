import { useCallback, useEffect, useRef, useState } from "react";

export function useCopyFeedback(resetAfter = 1_600) {
  const [copied, setCopied] = useState("");
  const timer = useRef<number | undefined>(undefined);

  const lifetime = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => {
      controller.abort();
      window.clearTimeout(timer.current);
    };
  }, []);

  const copy = useCallback(
    async (text: string, key = text) => {
      const signal = lifetime.current?.signal;
      if (!signal || signal.aborted) return;
      await navigator.clipboard.writeText(text);
      if (signal.aborted) return;
      setCopied(key);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(""), resetAfter);
    },
    [resetAfter],
  );

  return { copied, copy };
}
