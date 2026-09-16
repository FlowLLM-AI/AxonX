import { useCallback, useEffect, useRef, useState } from "react";

export function useCopyFeedback(resetAfter = 1_600) {
  const [copied, setCopied] = useState("");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = useCallback(
    async (text: string, key = text) => {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(""), resetAfter);
    },
    [resetAfter],
  );

  return { copied, copy };
}
