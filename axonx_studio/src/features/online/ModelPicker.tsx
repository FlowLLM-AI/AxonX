import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Select-only combobox: keep the menu in the page instead of the OS popup. */
export function ModelPicker({
  models,
  value,
  onChange,
}: {
  models: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const active = Math.min(index, models.length - 1);
  const show = () => {
    setIndex(Math.max(0, models.indexOf(value)));
    setOpen(true);
  };
  const choose = (model: string) => {
    onChange(model);
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  useEffect(() => {
    if (open)
      document
        .getElementById(`${id}-${active}`)
        ?.scrollIntoView?.({ block: "nearest" });
  }, [open, active, id]);
  return (
    <div
      className="online-model-select"
      ref={wrapper}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="online-model-picker"
        role="combobox"
        aria-label={t("onlineWorkbench.model")}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        disabled={!models.length}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(event) => {
          if (event.key === "Tab") {
            setOpen(false);
            return;
          }
          if (event.key === "Escape") {
            if (open) event.stopPropagation();
            setOpen(false);
            return;
          }
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            if (!open) {
              show();
              if (event.key === "Home") setIndex(0);
              if (event.key === "End") setIndex(models.length - 1);
              return;
            }
            setIndex(
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? models.length - 1
                  : (active +
                      (event.key === "ArrowDown" ? 1 : -1) +
                      models.length) %
                    models.length,
            );
          } else if (open && ["Enter", " "].includes(event.key)) {
            event.preventDefault();
            choose(models[active]);
          } else if (
            event.key.length === 1 &&
            !event.ctrlKey &&
            !event.metaKey &&
            event.key !== " "
          ) {
            const match = models.findIndex((model) =>
              model.toLowerCase().startsWith(event.key.toLowerCase()),
            );
            if (match >= 0) {
              event.preventDefault();
              setIndex(match);
              setOpen(true);
            }
          }
        }}
      >
        <span>{t("onlineWorkbench.model")}</span>
        <strong title={value}>{value || "—"}</strong>
        <ChevronDown aria-hidden="true" />
      </button>
      {open && (
        <div
          id={id}
          className="online-model-options"
          role="listbox"
          aria-label={t("onlineWorkbench.model")}
        >
          {models.map((model, option) => (
            <button
              type="button"
              role="option"
              id={`${id}-${option}`}
              key={model}
              tabIndex={-1}
              aria-selected={model === value}
              className={active === option ? "highlighted" : ""}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setIndex(option)}
              onClick={() => choose(model)}
            >
              <span className="online-model-check">
                {model === value && <Check aria-hidden="true" />}
              </span>
              <span>{model}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
