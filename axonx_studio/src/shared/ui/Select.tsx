import { Check, ChevronDown } from "lucide-react";
import type { CSSProperties, ReactNode, SelectHTMLAttributes } from "react";
import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

function optionText(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children: ReactNode }>(child)
        ? optionText(child.props.children)
        : String(child),
    )
    .join("");
}

/** Select-only combobox: keep the menu in the page instead of the OS popup. */
export function Picker({
  options,
  value,
  onChange,
  label,
  className = "",
  id: triggerId,
  disabled,
  ariaLabel,
  labelledBy,
  describedBy,
  required,
}: {
  label?: string;
  ariaLabel?: string;
  labelledBy?: string;
  describedBy?: string;
  required?: boolean;
  options: { value: string; label: ReactNode; disabled?: boolean }[];
  className?: string;
  id?: string;
  disabled?: boolean;
  value: string;
  onChange: (value: string) => void;
}) {
  const enabled = options.filter((option) => !option.disabled);
  const values = enabled.map((option) => option.value);
  const selected =
    options.find((option) => option.value === value) || options[0];
  const menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<CSSProperties>({});
  const id = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const expanded = open && !disabled && values.length > 0;
  const active = Math.min(index, values.length - 1);
  const activeId = `${id}-${options.findIndex((option) => option.value === values[active])}`;
  const show = () => {
    setIndex(Math.max(0, values.indexOf(value)));
    setOpen(true);
  };
  const choose = (model: string) => {
    onChange(model);
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!expanded) return;
    const outside = (event: PointerEvent) => {
      if (
        !wrapper.current?.contains(event.target as Node) &&
        !menu.current?.contains(event.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [expanded]);
  useEffect(() => {
    if (expanded)
      document.getElementById(activeId)?.scrollIntoView?.({ block: "nearest" });
  }, [expanded, activeId]);
  useLayoutEffect(() => {
    if (!expanded) return;
    const place = () => {
      const rect = trigger.current!.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - 16;
      const above = rect.top - 16;
      const upward = below < 180 && above > below;
      const left = Math.max(
        8,
        Math.min(rect.left, window.innerWidth - Math.max(rect.width, 240) - 8),
      );
      setPosition({
        left,
        minWidth: Math.min(rect.width, window.innerWidth - 16),
        maxWidth: Math.min(
          Math.max(rect.width, 360),
          window.innerWidth - left - 8,
        ),
        maxHeight: Math.max(64, Math.min(280, upward ? above : below)),
        ...(upward
          ? { bottom: window.innerHeight - rect.top + 8 }
          : { top: rect.bottom + 8 }),
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [expanded]);
  return (
    <div
      className="select-control"
      ref={wrapper}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <button
        ref={trigger}
        type="button"
        id={triggerId}
        className={`select-trigger ${className}`}
        value={selected?.value || ""}
        role="combobox"
        aria-label={ariaLabel || label}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        aria-required={required || undefined}
        aria-haspopup="listbox"
        aria-expanded={expanded}
        aria-controls={expanded ? id : undefined}
        aria-activedescendant={expanded && active >= 0 ? activeId : undefined}
        disabled={disabled || !values.length}
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
              if (event.key === "End") setIndex(values.length - 1);
              return;
            }
            setIndex(
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? values.length - 1
                  : (active +
                      (event.key === "ArrowDown" ? 1 : -1) +
                      values.length) %
                    values.length,
            );
          } else if (open && ["Enter", " "].includes(event.key)) {
            event.preventDefault();
            choose(values[active]);
          } else if (
            event.key.length === 1 &&
            !event.ctrlKey &&
            !event.metaKey &&
            event.key !== " "
          ) {
            const match = enabled.findIndex((option) =>
              optionText(option.label || option.value)
                .toLowerCase()
                .startsWith(event.key.toLowerCase()),
            );
            if (match >= 0) {
              event.preventDefault();
              setIndex(match);
              setOpen(true);
            }
          }
        }}
      >
        {label && <span className="select-label">{label}</span>}
        <strong title={optionText(selected?.label)}>
          {selected?.label || "—"}
        </strong>
        <ChevronDown aria-hidden="true" />
      </button>
      {expanded &&
        createPortal(
          <div
            ref={menu}
            style={position}
            id={id}
            className="select-options"
            role="listbox"
            aria-label={ariaLabel || label}
            aria-labelledby={labelledBy}
          >
            {options.map(({ value: model, label, disabled }, optionIndex) => (
              <button
                type="button"
                role="option"
                id={`${id}-${optionIndex}`}
                key={model}
                tabIndex={-1}
                aria-selected={model === value}
                disabled={disabled}
                className={values[active] === model ? "highlighted" : ""}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() =>
                  !disabled && setIndex(values.indexOf(model))
                }
                onClick={(event) => {
                  event.preventDefault();
                  choose(model);
                }}
              >
                <span className="select-check">
                  {model === value && <Check aria-hidden="true" />}
                </span>
                <span>{label}</span>
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}

/** Native select handles form submission/validation; Picker provides the visible UI. */
export function Select({
  children,
  onChange,
  className,
  id,
  ...props
}: Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "value" | "defaultValue" | "multiple"
> & { value: string | number }) {
  const native = useRef<HTMLSelectElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const options = Children.toArray(children)
    .filter(
      isValidElement<{
        value: string | number;
        disabled?: boolean;
        children: ReactNode;
      }>,
    )
    .map(({ props }) => ({
      value: String(props.value),
      label: props.children,
      disabled: props.disabled,
    }));
  return (
    <div className="select-field" ref={wrapper}>
      <Picker
        id={id}
        className={className}
        ariaLabel={props["aria-label"]}
        labelledBy={props["aria-labelledby"]}
        describedBy={props["aria-describedby"]}
        required={props.required}
        options={options}
        value={String(props.value ?? "")}
        disabled={props.disabled}
        onChange={(value) => {
          native.current!.value = value;
          native.current!.dispatchEvent(new Event("change", { bubbles: true }));
        }}
      />
      <select
        {...props}
        ref={native}
        className="select-native"
        aria-hidden="true"
        tabIndex={-1}
        onChange={onChange}
        onInvalid={(event) => {
          event.preventDefault();
          wrapper.current
            ?.querySelector<HTMLButtonElement>("[role=combobox]")
            ?.focus();
        }}
      >
        {children}
      </select>
    </div>
  );
}
