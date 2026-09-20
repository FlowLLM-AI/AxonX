import { describe, expect, it } from "vitest";
import type { JsonSchema } from "./types";
import {
  decodeFieldValue,
  initialSchemaValues,
  parseSchemaValues,
  schemaType,
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

  it("submits comma-separated source tasks as an array", () => {
    const sourceSchema: JsonSchema = {
      properties: { source_tasks: { type: "array", default: [] } },
    };
    expect(initialSchemaValues(sourceSchema).source_tasks).toBe("");
    expect(
      parseSchemaValues(
        sourceSchema,
        { source_tasks: "etl#one#first, etl#two#second" },
        { required: "required", invalidJson: "invalid" },
      ).data.source_tasks,
    ).toEqual(["etl#one#first", "etl#two#second"]);
  });
});
