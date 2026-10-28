// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { parseSchemaValues, type SchemaFormValues } from "../schema/values";
import { SchemaForm, SchemaOutput } from "./SchemaForm";

afterEach(() => vi.unstubAllGlobals());

it("presents output fields and resolved types without editable controls", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <SchemaOutput
          schema={{
            $defs: { Record: { type: "object" } },
            required: ["result"],
            properties: {
              result: {
                type: "number",
                title: "Result",
                description: "Sum of operands",
              },
              records: { type: "array", items: { $ref: "#/$defs/Record" } },
            },
          }}
        />,
      ),
    );
    expect(container.querySelectorAll("article")).toHaveLength(2);
    expect(container.textContent).toContain("Sum of operands");
    expect(container.textContent).toContain("object[]");
    expect(container.querySelector("input, textarea, pre, details")).toBeNull();
  } finally {
    await act(async () => root.unmount());
  }
});

it("edits string arrays with add/remove controls and submits an array", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  const schema = {
    properties: {
      upstream_task_ids: { type: "array", items: { type: "string" } },
    },
  };
  let latest: SchemaFormValues = {};
  function Form() {
    const [values, setValues] = useState<SchemaFormValues>({
      upstream_task_ids: "[]",
    });
    latest = values;
    return <SchemaForm schema={schema} values={values} onChange={setValues} />;
  }
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<Form />));
    expect(container.querySelector("textarea")).toBeNull();
    const add = container.querySelector<HTMLButtonElement>(".string-list-add")!;
    await act(async () => add.click());
    await act(async () => add.click());
    expect(container.querySelectorAll("input")).toHaveLength(2);
    const values = ["etl#source#first", "train#model#second"];
    for (const [index, input] of [
      ...container.querySelectorAll("input"),
    ].entries()) {
      await act(async () => {
        Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          "value",
        )!.set!.call(input, values[index]);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    }
    expect(
      parseSchemaValues(schema, latest, {
        required: "required",
        invalidJson: "invalid",
      }).data.upstream_task_ids,
    ).toEqual(values);
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(".string-list-remove")!
        .click(),
    );
    expect(JSON.parse(String(latest.upstream_task_ids))).toEqual([values[1]]);
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>(".string-list-remove")!
        .click(),
    );
    expect(JSON.parse(String(latest.upstream_task_ids))).toEqual([]);
  } finally {
    await act(async () => root.unmount());
    container.remove();
  }
});

it("keeps object arrays as JSON fields", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <SchemaForm
          schema={{
            properties: {
              windows: { type: "array", items: { type: "object" } },
            },
          }}
          values={{ windows: "[]" }}
          onChange={() => {}}
        />,
      ),
    );
    expect(container.querySelectorAll("textarea")).toHaveLength(1);
    expect(container.querySelector(".string-list-add")).toBeNull();
  } finally {
    await act(async () => root.unmount());
  }
});
