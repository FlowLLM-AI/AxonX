import type { JobEvent } from "../shared/api/event";
const abortError = () => new DOMException("Aborted", "AbortError");

export function sse(
  next: () => JobEvent[],
  signal?: AbortSignal | null,
  onClose = () => {},
): Response {
  let stop = () => {};
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      let timer: ReturnType<typeof setTimeout>;
      let closed = false;
      const cleanup = () => {
        closed = true;
        clearTimeout(timer);
        signal?.removeEventListener("abort", abort);
        onClose();
      };
      const abort = () => {
        if (!closed) {
          cleanup();
          controller.error(abortError());
        }
      };
      stop = cleanup;
      const tick = () => {
        if (closed) return;
        try {
          for (const event of next()) {
            controller.enqueue(
              encoder.encode(`data: ${JSON.stringify(event)}\n\n`),
            );
            if (event.kind === "result") {
              cleanup();
              controller.close();
              return;
            }
          }
          timer = setTimeout(tick, 350);
        } catch (error) {
          cleanup();
          controller.error(error);
        }
      };
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) abort();
      else tick();
    },
    cancel() {
      stop();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}
