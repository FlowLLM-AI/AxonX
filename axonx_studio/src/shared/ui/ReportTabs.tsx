import { Fragment, useId, useState, type ReactNode } from "react";

type ReportTab = {
  id: string;
  label: ReactNode;
  content?: ReactNode;
  lazy?: boolean;
};

/** Keep panels mounted so tab changes preserve logs and report controls. */
export function ReportTabs({
  tabs,
  defaultTab,
  selected: controlled,
  onSelected,
  panelId,
  ariaLabel,
  separateFirst = false,
  connectors = true,
  actions,
}: {
  tabs: ReportTab[];
  defaultTab?: string;
  selected?: string;
  onSelected?: (id: string) => void;
  panelId?: string;
  ariaLabel?: string;
  separateFirst?: boolean;
  connectors?: boolean;
  actions?: ReactNode;
}) {
  const [selected, setSelected] = useState(defaultTab || tabs[0]?.id);
  const [visited, setVisited] = useState(
    () => new Set([defaultTab || tabs[0]?.id]),
  );
  const select = (id: string) => {
    setSelected(id);
    onSelected?.(id);
    setVisited((value) => new Set([...value, id]));
  };
  const prefix = useId();
  const value = controlled ?? selected;
  const active = tabs.some((tab) => tab.id === value) ? value : tabs[0]?.id;
  const buttons = tabs.map((tab, index) => (
    <button
      key={tab.id}
      type="button"
      role="tab"
      id={`${prefix}-${tab.id}-tab`}
      aria-controls={panelId || `${prefix}-${tab.id}-panel`}
      aria-selected={active === tab.id}
      tabIndex={active === tab.id ? 0 : -1}
      onClick={() => select(tab.id)}
      onKeyDown={(event) => {
        const next =
          event.key === "ArrowRight"
            ? (index + 1) % tabs.length
            : event.key === "ArrowLeft"
              ? (index + tabs.length - 1) % tabs.length
              : event.key === "Home"
                ? 0
                : event.key === "End"
                  ? tabs.length - 1
                  : null;
        if (next == null) return;
        event.preventDefault();
        select(tabs[next].id);
        const buttons = event.currentTarget
          .closest('[role="tablist"]')
          ?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
        buttons?.[next]?.focus();
      }}
    >
      {tab.label}
    </button>
  ));
  const navigation = (
    <div role="tablist" className="operation-tablist" aria-label={ariaLabel}>
      {separateFirst ? (
        <>
          {buttons[0]}
          <div className="operation-tab-group">
            {buttons.slice(1).map((button, index) => (
              <Fragment key={tabs[index + 1].id}>
                {connectors && index > 0 && (
                  <span className="operation-tab-connector" aria-hidden="true">
                    ›
                  </span>
                )}
                {button}
              </Fragment>
            ))}
          </div>
        </>
      ) : (
        buttons
      )}
    </div>
  );
  return (
    <div className="operation-tabs">
      {actions ? (
        <div className="operation-tabs-toolbar">
          {navigation}
          {actions}
        </div>
      ) : (
        navigation
      )}
      {tabs
        .filter((tab) => tab.content !== undefined)
        .map((tab) => (
          <section
            key={tab.id}
            role="tabpanel"
            id={`${prefix}-${tab.id}-panel`}
            aria-labelledby={`${prefix}-${tab.id}-tab`}
            hidden={active !== tab.id}
            tabIndex={0}
          >
            {(!tab.lazy || active === tab.id || visited.has(tab.id)) &&
              tab.content}
          </section>
        ))}
    </div>
  );
}
