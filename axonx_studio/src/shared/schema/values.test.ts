import { describe, expect, it } from "vitest";
import type { JsonSchema } from "./values";
import {
  decodeFieldValue,
  initialSchemaValues,
  parseSchemaValues,
  schemaType,
  formSchema,
} from "./values";

const schema: JsonSchema = {
  type: "object",
  required: ["count", "config"],
  properties: {
    count: { type: "integer", default: 3 },
    enabled: { type: "boolean", default: true },
    mode: { type: "string", enum: ["fast", "safe"], default: "safe" },
    config: { type: "object" },
  },
};

describe("JSON schema values", () => {
  it("resolves nullable object references while preserving field defaults", () => {
    const schema = formSchema({
      $defs: {
        Options: { type: "object", properties: { count: { type: "integer" } } },
      },
      properties: {
        config: {
          anyOf: [{ $ref: "#/$defs/Options" }, { type: "null" }],
          default: { count: 2 },
        },
      },
    });
    expect(schemaType(schema.properties!.config)).toBe("object");
    const defaults = initialSchemaValues(schema);
    expect(
      parseSchemaValues(schema, defaults, {
        required: "required",
        invalidJson: "invalid",
      }).data.config,
    ).toEqual({ count: 2 });
  });
  it("rejects non-finite numbers and fractional integers", () => {
    expect(() => decodeFieldValue("1.5", { type: "integer" })).toThrow();
    expect(() => decodeFieldValue("Infinity", { type: "number" })).toThrow();
  });
  it("keeps nullable array defaults empty and resolves referenced item types", () => {
    const schema = formSchema({
      $defs: {
        Window: { type: "object", properties: { date: { type: "string" } } },
      },
      properties: {
        tags: {
          anyOf: [
            { type: "array", items: { type: "string" } },
            { type: "null" },
          ],
          default: null,
        },
        windows: { type: "array", items: { $ref: "#/$defs/Window" } },
      },
    });
    expect(initialSchemaValues(schema).tags).toBe("");
    expect(schema.properties!.windows.items!.type).toBe("object");
  });
  it("resolves nullable and anyOf types", () => {
    expect(schemaType({ type: ["null", "number"] })).toBe("number");
    expect(schemaType({ anyOf: [{ type: "null" }, { type: "array" }] })).toBe(
      "array",
    );
  });

  it("creates editable defaults", () => {
    expect(initialSchemaValues(schema)).toEqual({
      count: "3",
      enabled: true,
      mode: '"safe"',
      config: "",
    });
  });

  it("decodes typed values", () => {
    expect(decodeFieldValue("42", { type: "integer" })).toBe(42);
    expect(decodeFieldValue('["a"]', { type: "array" })).toEqual(["a"]);
    expect(decodeFieldValue('"fast"', { enum: ["fast", "safe"] })).toBe("fast");
  });

  it("returns field errors without losing valid data", () => {
    const result = parseSchemaValues(
      schema,
      {
        count: "7",
        enabled: false,
        mode: '"fast"',
        config: "not-json",
      },
      { required: "required", invalidJson: "invalid" },
    );
    expect(result.data).toEqual({ count: 7, enabled: false, mode: "fast" });
    expect(result.errors).toEqual({ config: "invalid" });
  });

  it("submits upstream Task IDs as an array", () => {
    const sourceSchema: JsonSchema = {
      properties: {
        upstream_task_ids: { type: "array", items: { type: "string" } },
      },
    };
    expect(initialSchemaValues(sourceSchema).upstream_task_ids).toBe("");
    expect(
      parseSchemaValues(
        sourceSchema,
        { upstream_task_ids: '["etl#one#first", "etl#two#second"]' },
        { required: "required", invalidJson: "invalid" },
      ).data.upstream_task_ids,
    ).toEqual(["etl#one#first", "etl#two#second"]);
  });
});
