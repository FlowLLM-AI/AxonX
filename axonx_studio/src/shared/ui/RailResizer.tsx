import { useRef } from "react";
import { useTranslation } from "react-i18next";

export function RailResizer({
  min,
  max,
  className = "",
  onResize,
  onResizeEnd,
}: {
  min: number;
  max: number;
  className?: string;
  onResize?: (width: number) => void;
  onResizeEnd?: (width: number) => void;
}) {
  const { t } = useTranslation();
  const handleRef = useRef<HTMLDivElement>(null);

  const resizeTo = (panel: HTMLElement, width: number) => {
    const next = Math.max(min, Math.min(max, width));
    if (onResize) onResize(next);
    else {
      panel.style.width = `${next}px`;
      panel.style.flexBasis = `${next}px`;
    }
    return next;
  };

  return (
    <div
      ref={handleRef}
      className={`rail-resizer ${className}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={t("common.resizePanel")}
      tabIndex={0}
      onPointerDown={(event) => {
        const panel = handleRef.current
          ?.previousElementSibling as HTMLElement | null;
        if (!panel) return;
        event.preventDefault();
        const startX = event.clientX;
        const startWidth = panel.getBoundingClientRect().width;
        let currentWidth = startWidth;
        event.currentTarget.setPointerCapture(event.pointerId);
        const move = (moveEvent: PointerEvent) => {
          currentWidth = resizeTo(
            panel,
            startWidth + moveEvent.clientX - startX,
          );
        };
        const stop = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", stop);
          document.body.classList.remove("resizing-rail");
          onResizeEnd?.(currentWidth);
        };
        document.body.classList.add("resizing-rail");
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", stop, { once: true });
      }}
      onKeyDown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        const panel = handleRef.current
          ?.previousElementSibling as HTMLElement | null;
        if (!panel) return;
        event.preventDefault();
        const next = resizeTo(
          panel,
          panel.getBoundingClientRect().width +
            (event.key === "ArrowRight" ? 16 : -16),
        );
        onResizeEnd?.(next);
      }}
    />
  );
}
