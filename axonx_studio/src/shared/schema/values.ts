export interface JsonSchema {
  $defs?: Record<string, JsonSchema>;
  $ref?: string;
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchema[];
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  format?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
}

/** Resolve field references for controls; nested objects remain editable JSON. */
export function formSchema(schema: JsonSchema): JsonSchema {
  const resolve = (field: JsonSchema, seen = new Set<string>()): JsonSchema => {
    let resolved = field;
    if (field.$ref?.startsWith("#/$defs/") && !seen.has(field.$ref)) {
      const definition = schema.$defs?.[field.$ref.slice(8)];
      seen = new Set([...seen, field.$ref]);
      if (definition) resolved = { ...resolve(definition, seen), ...field };
    }
    const branch = resolved.anyOf?.find((item) => item.type !== "null");
    if (branch) resolved = { ...resolve(branch, seen), ...resolved };
    return resolved.items
      ? { ...resolved, items: resolve(resolved.items, seen) }
      : resolved;
  };
  return {
    ...schema,
    properties: Object.fromEntries(
      Object.entries(schema.properties || {}).map(([key, field]) => [
        key,
        resolve(field),
      ]),
    ),
  };
}

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

function encodeFieldValue(
  value: unknown,
  schema: JsonSchema,
): SchemaFieldValue {
  if (value === null) return "";
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
  if (type === "integer" || type === "number") {
    const number = Number(value);
    if (
      !Number.isFinite(number) ||
      (type === "integer" && !Number.isInteger(number))
    )
      throw new Error("Invalid number");
    return number;
  }
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
