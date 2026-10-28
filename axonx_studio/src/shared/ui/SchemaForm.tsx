import { useTranslation } from "react-i18next";
import type { JsonSchema } from "../schema/values";
import {
  schemaType,
  formSchema,
  type SchemaFieldValue,
  type SchemaFormValues,
} from "../schema/values";
import { Select } from "./Select";
import { Plus, X } from "lucide-react";

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

export function SchemaOutput({ schema }: { schema: JsonSchema }) {
  const { t } = useTranslation();
  const resolved = formSchema(schema);
  return (
    <div className="schema-fields schema-output-fields">
      {Object.entries(resolved.properties || {}).map(([name, field]) => {
        const type = schemaType(field);
        const label =
          type === "array"
            ? `${field.items ? schemaType(field.items) : "unknown"}[]`
            : type;
        return (
          <article key={name}>
            <header>
              <strong>{field.title || name}</strong>
              <code>{label}</code>
            </header>
            <span>
              <code>{name}</code>
              <small>
                {t(
                  (resolved.required || []).includes(name)
                    ? "schemaForm.requiredOutput"
                    : "schemaForm.optionalOutput",
                )}
              </small>
            </span>
            {field.description && <p>{field.description}</p>}
            {field.enum && (
              <p>
                {field.enum.map((value) => JSON.stringify(value)).join(" · ")}
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
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
  const stringList = type === "array" && schema.items?.type === "string";
  const items: string[] = stringList ? JSON.parse(String(value || "[]")) : [];
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
      ) : stringList ? (
        <div className="string-list-field">
          {items.map((item, index) => (
            <div key={index}>
              <input
                id={index === 0 ? id : `${id}-${index}`}
                type="text"
                aria-label={`${schema.title || name} ${index + 1}`}
                value={item}
                minLength={schema.items?.minLength}
                maxLength={schema.items?.maxLength}
                pattern={schema.items?.pattern}
                onChange={(event) =>
                  onChange(
                    JSON.stringify(
                      items.map((value, at) =>
                        at === index ? event.target.value : value,
                      ),
                    ),
                  )
                }
              />
              <button
                type="button"
                className="string-list-remove"
                aria-label={t("schemaForm.removeItem", { index: index + 1 })}
                onClick={() =>
                  onChange(
                    JSON.stringify(items.filter((_, at) => at !== index)),
                  )
                }
              >
                <X />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="string-list-add"
            onClick={() => onChange(JSON.stringify([...items, ""]))}
          >
            <Plus />
            {t("schemaForm.addItem")}
          </button>
        </div>
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
          minLength={schema.minLength}
          maxLength={schema.maxLength}
          pattern={schema.pattern}
          value={String(value)}
          required={required}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
