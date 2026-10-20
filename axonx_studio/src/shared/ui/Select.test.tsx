// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Select } from "./Select";

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});
const trigger = () =>
  container.querySelector<HTMLButtonElement>("[role=combobox]")!;
const key = (key: string) =>
  act(async () => {
    trigger().dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true }),
    );
  });

it("selects through the visible menu and preserves change events and form data", async () => {
  const changed = vi.fn();
  function Form() {
    const [value, setValue] = useState("a");
    return (
      <form>
        <Select
          name="pool"
          aria-label="Stock pool"
          value={value}
          onChange={(event) => {
            changed(event.target.value);
            setValue(event.target.value);
          }}
        >
          <option value="a">All stocks</option>
          <option value="b">Buyable stocks</option>
        </Select>
      </form>
    );
  }
  await act(async () => root.render(<Form />));
  expect(trigger().getAttribute("aria-label")).toBe("Stock pool");
  await act(async () => trigger().click());
  expect(container.querySelector("[role=listbox]")).toBeNull();
  await act(async () =>
    document.querySelectorAll<HTMLButtonElement>("[role=option]")[1].click(),
  );
  expect(changed.mock.calls).toEqual([["b"]]);
  expect(trigger().textContent).toBe("Buyable stocks");
  expect(new FormData(container.querySelector("form")!).get("pool")).toBe("b");
  expect(document.querySelector("[role=listbox]")).toBeNull();
  expect(document.activeElement).toBe(trigger());
});

it("skips disabled choices with arrows, Home, End and type-ahead", async () => {
  const changed = vi.fn();
  await act(async () =>
    root.render(
      <Select value="a" onChange={(event) => changed(event.target.value)}>
        <option value="a">Alpha</option>
        <option value="b" disabled>
          Beta
        </option>
        <option value="c">Charlie</option>
        <option value="d" disabled>
          Delta
        </option>
      </Select>,
    ),
  );
  await key("ArrowDown");
  const scroll = vi.fn();
  document.querySelectorAll<HTMLElement>("[role=option]")[2].scrollIntoView =
    scroll;
  await key("ArrowDown");
  expect(scroll).toHaveBeenCalledWith({ block: "nearest" });
  const active = trigger().getAttribute("aria-activedescendant")!;
  expect(document.getElementById(active)?.textContent).toBe("Charlie");
  await key("Home");
  await key("End");
  await key("Enter");
  expect(changed).toHaveBeenCalledWith("c");
  await key("b");
  expect(trigger().getAttribute("aria-expanded")).toBe("false");
  await key("c");
  await key("Escape");
  expect(document.querySelector("[role=listbox]")).toBeNull();
});

it("retains required validation and focuses the visible labelled control", async () => {
  await act(async () =>
    root.render(
      <form>
        <label htmlFor="pool">Pool</label>
        <Select id="pool" value="" required>
          <option value="">Choose</option>
          <option value="all">All</option>
        </Select>
      </form>,
    ),
  );
  let valid = true;
  await act(async () => {
    valid = container.querySelector("form")!.checkValidity();
  });
  expect(valid).toBe(false);
  expect(document.activeElement).toBe(trigger());
  expect(trigger().id).toBe("pool");
  expect(trigger().getAttribute("aria-required")).toBe("true");
});

it("places menus above a low trigger, closes outside, and disables empty controls", async () => {
  await act(async () =>
    root.render(
      <Select value="a">
        <option value="a">Alpha</option>
      </Select>,
    ),
  );
  vi.spyOn(trigger(), "getBoundingClientRect").mockReturnValue({
    left: 300,
    top: 700,
    bottom: 740,
    width: 140,
  } as DOMRect);
  await act(async () => trigger().click());
  const menu = document.querySelector<HTMLDivElement>("[role=listbox]")!;
  expect(menu.style.bottom).not.toBe("");
  await act(async () =>
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true })),
  );
  expect(document.querySelector("[role=listbox]")).toBeNull();
  await act(async () => root.render(<Select value="" />));
  expect(trigger().disabled).toBe(true);
});

it("associates an implicit label with the visible trigger", async () => {
  await act(async () =>
    root.render(
      <label>
        Pool
        <Select value="all">
          <option value="all">All stocks</option>
        </Select>
      </label>,
    ),
  );
  expect(container.querySelector("label")!.control).toBe(trigger());
});

it("constrains a wide control's popup to a narrow viewport", async () => {
  vi.stubGlobal("innerWidth", 390);
  await act(async () =>
    root.render(
      <Select value="a">
        <option value="a">A long option</option>
      </Select>,
    ),
  );
  vi.spyOn(trigger(), "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 100,
    bottom: 140,
    width: 600,
  } as DOMRect);
  await act(async () => trigger().click());
  const menu = document.querySelector<HTMLDivElement>("[role=listbox]")!;
  expect(parseFloat(menu.style.left)).toBeGreaterThanOrEqual(8);
  expect(
    parseFloat(menu.style.left) + parseFloat(menu.style.maxWidth),
  ).toBeLessThanOrEqual(382);
});
