import { useEffect } from "react";
import { startPolling } from "../lib/polling";

type Subscriber = {
  callback: (signal: AbortSignal) => Promise<unknown>;
  controller: AbortController;
  enabled: boolean;
  pending?: Promise<unknown>;
  onSeconds?: (seconds: number) => void;
};
class RefreshScheduler {
  private readonly subscribers = new Set<Subscriber>();
  private stop?: () => void;
  private run(subscriber: Subscriber) {
    subscriber.pending ??= Promise.resolve()
      .then(() =>
        subscriber.controller.signal.aborted
          ? undefined
          : subscriber.callback(subscriber.controller.signal),
      )
      .finally(() => {
        subscriber.pending = undefined;
      });
    return subscriber.pending;
  }
  readonly refresh = async (automatic = false) => {
    await Promise.allSettled(
      [...this.subscribers]
        .filter((s) => !automatic || s.enabled)
        .map((s) => this.run(s)),
    );
  };
  subscribe(
    callback: Subscriber["callback"],
    enabled: boolean,
    immediate: boolean,
    onSeconds?: Subscriber["onSeconds"],
  ) {
    const subscriber: Subscriber = {
      callback,
      enabled,
      onSeconds,
      controller: new AbortController(),
    };
    this.subscribers.add(subscriber);
    onSeconds?.(60);
    if (!this.stop && enabled)
      this.stop = startPolling(
        async () => {
          void this.refresh(true);
        },
        60,
        (seconds) => {
          for (const listener of this.subscribers)
            listener.onSeconds?.(seconds);
        },
        false,
        false,
      );
    if (enabled && immediate) void this.run(subscriber).catch(() => {});
    return () => {
      subscriber.controller.abort();
      this.subscribers.delete(subscriber);
      if (![...this.subscribers].some((s) => s.enabled)) {
        this.stop?.();
        this.stop = undefined;
      }
    };
  }
}
const scheduler = new RefreshScheduler();
/** Mounted pages and log viewers share one visible-page clock and manual refresh. */
export function useRefresh(
  callback: Subscriber["callback"],
  enabled = true,
  immediate = false,
  onSeconds?: Subscriber["onSeconds"],
) {
  useEffect(
    () => scheduler.subscribe(callback, enabled, immediate, onSeconds),
    [callback, enabled, immediate, onSeconds],
  );
  return scheduler.refresh;
}
