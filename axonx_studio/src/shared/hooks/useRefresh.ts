import { useEffect } from "react";
import { startPolling } from "../lib/polling";

type Subscriber = {
  callback: (signal: AbortSignal) => Promise<unknown>;
  controller: AbortController;
  enabled: boolean;
  pending?: Promise<unknown>;
  onSeconds?: (seconds: number) => void;
};
const subscribers = new Set<Subscriber>();
let stop: (() => void) | undefined;
/** Deduplicate each subscriber without letting an obsolete request block new pages. */
function run(subscriber: Subscriber) {
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

/** Every mounted page and log viewer shares this single 60-second clock. */
async function refresh(automatic = false) {
  await Promise.allSettled(
    [...subscribers]
      .filter((subscriber) => !automatic || subscriber.enabled)
      .map(run),
  );
}

export function useRefresh(
  callback: Subscriber["callback"],
  enabled = true,
  immediate = false,
  onSeconds?: Subscriber["onSeconds"],
) {
  useEffect(() => {
    const subscriber = {
      callback,
      controller: new AbortController(),
      enabled,
      onSeconds,
    };
    subscribers.add(subscriber);
    onSeconds?.(60);
    if (!stop && enabled)
      stop = startPolling(
        async () => {
          void refresh(true);
        },
        60,
        (seconds) => {
          for (const listener of subscribers) listener.onSeconds?.(seconds);
        },
        false,
        false,
      );
    if (enabled && immediate) void run(subscriber).catch(() => {});
    return () => {
      subscriber.controller.abort();
      subscribers.delete(subscriber);
      if (![...subscribers].some((subscriber) => subscriber.enabled)) {
        stop?.();
        stop = undefined;
      }
    };
  }, [callback, enabled, immediate, onSeconds]);
  return refreshNow;
}

const refreshNow = () => refresh();
