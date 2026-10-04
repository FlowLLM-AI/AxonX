/** Poll only while visible, with at most one callback running per subscription. */
export function startPolling(
  callback: (signal: AbortSignal) => Promise<void>,
  intervalSeconds: number,
  onSeconds: (seconds: number) => void,
  immediate = false,
) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setInterval> | undefined;
  let remaining = intervalSeconds;
  let pending = false;

  const reset = () => {
    remaining = intervalSeconds;
    onSeconds(remaining);
  };
  const run = async () => {
    if (pending || document.hidden || controller.signal.aborted) return;
    pending = true;
    try {
      await callback(controller.signal);
    } catch {
      // Callers report request failures; keep future polling alive.
    } finally {
      pending = false;
      if (!controller.signal.aborted) reset();
    }
  };
  const start = () => {
    timer = setInterval(() => {
      if (document.hidden || pending) return;
      remaining -= 1;
      if (remaining <= 0) {
        reset();
        void run();
      } else onSeconds(remaining);
    }, 1_000);
  };
  const visibilityChanged = () => {
    clearInterval(timer);
    reset();
    if (!document.hidden) {
      void run();
      start();
    }
  };

  reset();
  if (!document.hidden) {
    if (immediate) void run();
    start();
  }
  document.addEventListener("visibilitychange", visibilityChanged);
  return () => {
    controller.abort();
    clearInterval(timer);
    document.removeEventListener("visibilitychange", visibilityChanged);
  };
}
