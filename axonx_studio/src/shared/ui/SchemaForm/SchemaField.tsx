import { t } from "../../../i18n";
import type { JsonSchema, Language } from "../../../types";
import { humanizeFieldName, schemaType } from "../../schema/values";
import type { SchemaFieldValue } from "../../schema/values";

interface SchemaFieldProps {
  name: string;
  schema: JsonSchema;
  required: boolean;
  value: SchemaFieldValue;
  error?: string;
  language: Language;
  variant?: "default" | "compact";
  onChange: (value: SchemaFieldValue) => void;
}

export function SchemaField({
  name,
  schema,
  required,
  value,
  error,
  language,
  variant = "default",
  onChange,
}: SchemaFieldProps) {
  const text = t(language);
  const type = schemaType(schema);
  const id = `field-${variant}-${name}`;
  const title =
    schema.title || (variant === "default" ? humanizeFieldName(name) : name);
  const requirement = (
    <em className={required ? "required" : ""}>
      {required ? text.required : text.optional}
    </em>
  );
  const content = (
    <>
      {variant === "default" ? (
        <div className="field-label">
          <span>{title}</span>
          {requirement}
        </div>
      ) : (
        <span>
          <strong>{title}</strong>
          {requirement}
        </span>
      )}
      {schema.description && <small>{schema.description}</small>}
      {schema.enum ? (
        <select
          id={id}
          value={String(value)}
          required={required}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{variant === "default" ? text.choose : "—"}</option>
          {schema.enum.map((item) => (
            <option key={JSON.stringify(item)} value={JSON.stringify(item)}>
              {String(item)}
            </option>
          ))}
        </select>
      ) : type === "boolean" ? (
        <button
          id={id}
          type="button"
          className={`switch-control ${value ? "on" : ""}`}
          onClick={() => onChange(!value)}
          role="switch"
          aria-checked={Boolean(value)}
        >
          <i />
          <span>{value ? "True" : "False"}</span>
        </button>
      ) : type === "object" || type === "array" ? (
        <textarea
          id={id}
          value={String(value)}
          required={required}
          placeholder={type === "array" ? "[]" : "{}"}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          id={id}
          type={
            type === "integer" || type === "number"
              ? "number"
              : schema.format === "date"
                ? "date"
                : "text"
          }
          step={type === "integer" ? 1 : type === "number" ? "any" : undefined}
          min={schema.minimum}
          max={schema.maximum}
          value={String(value)}
          required={required}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {error && <span className="field-error">{error}</span>}
    </>
  );

  return variant === "default" ? (
    <label
      className={`schema-field ${type === "object" || type === "array" ? "wide" : ""}`}
      htmlFor={id}
    >
      {content}
    </label>
  ) : (
    <label
      className={type === "object" || type === "array" ? "wide" : ""}
      htmlFor={id}
    >
      {content}
    </label>
  );
}
