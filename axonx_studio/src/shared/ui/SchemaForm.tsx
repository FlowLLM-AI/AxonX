import { useTranslation } from "react-i18next";
import type { JsonSchema } from "../schema/values";
import {
  schemaType,
  type SchemaFieldValue,
  type SchemaFormValues,
} from "../schema/values";
import { Select } from "./Select";

export function SchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: JsonSchema;
  values: SchemaFormValues;
  onChange: (values: SchemaFormValues) => void;
}) {
  return Object.entries(schema.properties || {}).map(([name, field]) => (
    <SchemaField
      key={name}
      name={name}
      schema={field}
      required={(schema.required || []).includes(name)}
      value={values[name] ?? ""}
      onChange={(value) => onChange({ ...values, [name]: value })}
    />
  ));
}
function SchemaField({
  name,
  schema,
  required,
  value,
  onChange,
}: {
  name: string;
  schema: JsonSchema;
  required: boolean;
  value: SchemaFieldValue;
  onChange: (value: SchemaFieldValue) => void;
}) {
  const { t } = useTranslation();
  const type = schemaType(schema);
  const id = `field-${name}`;
  const structured = type === "object" || type === "array";
  return (
    <label className={structured ? "wide" : ""} htmlFor={id}>
      <span>
        <strong>{schema.title || name}</strong>
        <em className={required ? "required" : ""}>
          {t(required ? "required" : "optional")}
        </em>
      </span>
      {schema.description && <small>{schema.description}</small>}
      {schema.enum ? (
        <Select
          id={id}
          value={String(value)}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">—</option>
          {schema.enum.map((item) => (
            <option key={JSON.stringify(item)} value={JSON.stringify(item)}>
              {String(item)}
            </option>
          ))}
        </Select>
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
          <span>{t(value ? "common.true" : "common.false")}</span>
        </button>
      ) : structured ? (
        <textarea
          id={id}
          value={String(value)}
          required={required}
          placeholder={type === "array" ? "[]" : "{}"}
          onChange={(e) => onChange(e.target.value)}
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
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
