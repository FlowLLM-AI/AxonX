import {
  ArrowRight,
  Braces,
  CheckCircle2,
  LoaderCircle,
  Network,
  Play,
  Search,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ContextOption } from "../../app/types";
import { axonx } from "../../shared/api/client";
import type { JobInfo } from "../../shared/api/types";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import type { SchemaFormValues } from "../../shared/schema/values";
import {
  initialSchemaValues,
  parseSchemaValues,
} from "../../shared/schema/values";
import { RailResizer } from "../../shared/ui/RailResizer";
import { SchemaForm } from "../../shared/ui/SchemaForm";
import type { MachineNode } from "../runtime/machine";

export default function ApiWorkspace({
  machine,
  initialName,
  onSelected,
  onOptionsChange,
  onConnection,
}: {
  machine: MachineNode;
  initialName?: string;
  onSelected: (name: string) => void;
  onOptionsChange?: (options: ContextOption[]) => void;
  onConnection: (online: boolean) => void;
}) {
  const { t } = useTranslation();
  const target = machine.isLocal ? undefined : machine.address;
  const selectedName = initialName || "";
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [values, setValues] = useState<SchemaFormValues>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<unknown>();

  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const catalog = await axonx.jobs({ target, signal });
        signal.throwIfAborted();
        onConnection(true);
        return catalog.items;
      } catch (reason) {
        if (!signal.aborted) onConnection(false);
        throw reason;
      }
    },
    [target, onConnection],
  );
  const { data, loading, error: catalogError, reload } = useAsyncResource(load);
  const apis = data ?? EMPTY_APIS;
  useEffect(() => {
    onOptionsChange?.(
      apis.map((api) => ({ value: api.name, label: api.name, detail: "POST" })),
    );
  }, [apis, onOptionsChange]);

  const selected = apis.find((item) => item.name === selectedName);
  const visible = useMemo(
    () =>
      apis.filter((item) =>
        `${item.name} ${item.description}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [apis, query],
  );
  useEffect(() => {
    if (!selected) return;
    setValues(initialSchemaValues(selected.input_schema));
    setResult(undefined);
    setError("");
  }, [selected]);

  const choose = onSelected;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const parsed = parseSchemaValues(selected.input_schema, values, {
      required: t("required"),
      invalidJson: t("jsonHint"),
    });
    if (Object.keys(parsed.errors).length) {
      setError(Object.values(parsed.errors)[0]);
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      setResult(
        await axonx.invoke(selected.name, parsed.data, {
          target: machine.isLocal ? undefined : machine.address,
        }),
      );
      onConnection(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      onConnection(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="api-workspace unified-workspace">
      <aside className="context-rail api-index rail-panel">
        <header className="rail-header">
          <div className="rail-heading">
            <small>PUBLIC API</small>
            <strong>{t("api.interfaces")}</strong>
          </div>
          <em>{apis.length}</em>
        </header>
        <label className="context-search rail-search">
          <Search />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("api.search")}
          />
        </label>
        <nav className="rail-scroll">
          {loading && !apis.length ? (
            <LoaderCircle className="spin context-loader" />
          ) : (
            visible.map((api) => (
              <button
                key={api.name}
                className={`rail-list-item${selectedName === api.name ? " active" : ""}`}
                onClick={() => choose(api.name)}
              >
                <Network />
                <span className="rail-item-copy">
                  <strong>{api.name}</strong>
                  <small>POST /jobs/{api.name}</small>
                </span>
                <ArrowRight />
              </button>
            ))
          )}
        </nav>
      </aside>
      <RailResizer min={180} max={440} className="context-resizer" />
      <main className="workspace-canvas api-canvas">
        {catalogError && (
          <div className="error-state" role="alert">
            {catalogError}
            <button onClick={() => void reload()}>{t("retry")}</button>
          </div>
        )}
        {!selected ? (
          <div className="empty-workspace">
            <Network />
            <strong>{t("api.select")}</strong>
          </div>
        ) : (
          <form onSubmit={submit}>
            <header className="canvas-heading api-heading">
              <div>
                <small>POST /jobs/{selected.name}</small>
                <h1>{selected.name}</h1>
                <p>{selected.description || t("api.noDescription")}</p>
              </div>
              <span>
                <CheckCircle2 />
                {t("api.available")}
              </span>
            </header>
            <section className="api-form-card">
              <header>
                <div>
                  <Braces />
                  <strong>{t("api.requestParameters")}</strong>
                </div>
                <small>
                  {Object.keys(selected.input_schema.properties || {}).length}{" "}
                  fields
                </small>
              </header>
              <div className="schema-fields">
                <SchemaForm
                  schema={selected.input_schema}
                  values={values}
                  onChange={setValues}
                />
              </div>
            </section>
            {error && <div className="inline-error">{error}</div>}
            <footer className="api-submit-row">
              <code>POST /jobs/{selected.name}</code>
              <button className="primary-button" disabled={submitting}>
                {submitting ? <LoaderCircle className="spin" /> : <Play />}
                {submitting ? t("api.calling") : t("api.call")}
              </button>
            </footer>
            {result !== undefined && (
              <section className="api-response">
                <header>
                  <span>
                    <i />
                    200
                  </span>
                  <strong>{t("api.response")}</strong>
                </header>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </section>
            )}
          </form>
        )}
      </main>
    </section>
  );
}

const EMPTY_APIS: JobInfo[] = [];
