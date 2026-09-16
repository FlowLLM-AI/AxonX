import type { JsonSchema } from "../../types";

export type SchemaFieldValue = string | boolean;
export type SchemaFormValues = Record<string, SchemaFieldValue>;

export function schemaType(schema: JsonSchema): string {
  if (Array.isArray(schema.type)) {
    return schema.type.find((type) => type !== "null") || "string";
  }
  if (schema.type) return schema.type;
  return (
    schema.anyOf?.map(schemaType).find((type) => type !== "null") || "string"
  );
}

export function encodeFieldValue(
  value: unknown,
  schema: JsonSchema,
): SchemaFieldValue {
  const type = schemaType(schema);
  if (type === "boolean") return Boolean(value);
  if (schema.enum || type === "object" || type === "array") {
    return value === undefined
      ? ""
      : JSON.stringify(
          value,
          null,
          type === "object" || type === "array" ? 2 : undefined,
        );
  }
  return String(value ?? "");
}

export function decodeFieldValue(
  value: SchemaFieldValue,
  schema: JsonSchema,
): unknown {
  const type = schemaType(schema);
  if (schema.enum) return JSON.parse(String(value));
  if (type === "boolean") return Boolean(value);
  if (type === "integer") return Number.parseInt(String(value), 10);
  if (type === "number") return Number(String(value));
  if (type === "object" || type === "array") return JSON.parse(String(value));
  return String(value);
}

export function initialSchemaValues(schema: JsonSchema): SchemaFormValues {
  return Object.fromEntries(
    Object.entries(schema.properties || {}).map(([name, field]) => [
      name,
      field.default !== undefined
        ? encodeFieldValue(field.default, field)
        : schemaType(field) === "boolean"
          ? false
          : "",
    ]),
  );
}

export function parseSchemaValues(
  schema: JsonSchema,
  values: SchemaFormValues,
  messages: { required: string; invalidJson: string },
): { data: Record<string, unknown>; errors: Record<string, string> } {
  const data: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  const required = new Set(schema.required || []);

  for (const [name, field] of Object.entries(schema.properties || {})) {
    const value = values[name];
    const type = schemaType(field);
    if ((value === "" || value === undefined) && required.has(name)) {
      errors[name] = messages.required;
      continue;
    }
    if (value === "" || value === undefined) continue;
    if (
      type === "boolean" &&
      value === false &&
      field.default === undefined &&
      !required.has(name)
    )
      continue;
    try {
      data[name] = decodeFieldValue(value, field);
    } catch {
      errors[name] = messages.invalidJson;
    }
  }

  return { data, errors };
}

export function humanizeFieldName(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
