import { useRef } from "react";

type Edge = 0 | 1;

export function DateRangeSlider({
  range,
  count,
  onChange,
  labels,
}: {
  range: [number, number];
  count: number;
  onChange: (edge: Edge, value: number) => void;
  labels: [string, string];
}) {
  const dragging = useRef<Edge | null>(null);
  const max = Math.max(0, count - 1);
  const position = (value: number) => `${max ? (value / max) * 100 : 0}%`;
  const atPointer = (clientX: number, element: HTMLDivElement) => {
    const bounds = element.getBoundingClientRect();
    return Math.round(
      Math.max(0, Math.min(1, (clientX - bounds.left) / bounds.width)) * max,
    );
  };
  const handleKey = (edge: Edge, event: React.KeyboardEvent) => {
    const current = range[edge];
    const next =
      event.key === "ArrowLeft" || event.key === "ArrowDown"
        ? current - 1
        : event.key === "ArrowRight" || event.key === "ArrowUp"
          ? current + 1
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? max
              : null;
    if (next !== null) {
      event.preventDefault();
      onChange(edge, Math.max(0, Math.min(max, next)));
    }
  };
  return (
    <div
      className="date-range-slider"
      onPointerDown={(event) => {
        const index = atPointer(event.clientX, event.currentTarget);
        const target = (event.target as HTMLElement).closest<HTMLElement>(
          "[data-edge]",
        );
        const edge = target
          ? (Number(target.dataset.edge) as Edge)
          : Math.abs(index - range[0]) <= Math.abs(index - range[1])
            ? 0
            : 1;
        dragging.current = edge;
        event.currentTarget.setPointerCapture(event.pointerId);
        onChange(edge, index);
      }}
      onPointerMove={(event) => {
        if (dragging.current !== null)
          onChange(
            dragging.current,
            atPointer(event.clientX, event.currentTarget),
          );
      }}
      onPointerUp={() => {
        dragging.current = null;
      }}
      onPointerCancel={() => {
        dragging.current = null;
      }}
      onLostPointerCapture={() => {
        dragging.current = null;
      }}
    >
      <div className="date-range-track" />
      <div
        className="date-range-selection"
        style={{
          left: position(range[0]),
          right: `${100 - (max ? (range[1] / max) * 100 : 0)}%`,
        }}
      />
      {([0, 1] as const).map((edge) => (
        <span
          key={edge}
          className="date-range-handle"
          data-edge={edge}
          role="slider"
          tabIndex={0}
          aria-label={labels[edge]}
          aria-valuemin={edge === 0 ? 0 : range[0]}
          aria-valuemax={edge === 0 ? range[1] : max}
          aria-valuenow={range[edge]}
          style={{ left: position(range[edge]) }}
          onKeyDown={(event) => handleKey(edge, event)}
        />
      ))}
    </div>
  );
}
