export function AxonXMark({
  className = "",
  labelled = false,
}: {
  className?: string;
  labelled?: boolean;
}) {
  return (
    <img
      className={`axonx-mark ${className}`.trim()}
      src="/axonx-icon.svg"
      alt={labelled ? "AxonX" : ""}
    />
  );
}
