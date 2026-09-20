import { describe, expect, it } from "vitest";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const sourceFiles = import.meta.glob("./**/*.{ts,tsx}", {
  eager: true,
  import: "default",
  query: "?raw",
}) as Record<string, string>;

function leafKeys(value: unknown, prefix = ""): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [prefix];
  }
  return Object.entries(value).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

function placeholders(value: unknown, prefix = ""): Record<string, string[]> {
  if (typeof value === "string") {
    return {
      [prefix]: [...value.matchAll(/{{\s*([^},\s]+).*?}}/g)]
        .map((match) => match[1])
        .sort(),
    };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.assign(
    {},
    ...Object.entries(value).map(([key, child]) =>
      placeholders(child, prefix ? `${prefix}.${key}` : key),
    ),
  );
}

function resourceValue(resource: object, key: string): unknown {
  return key
    .split(".")
    .reduce<unknown>(
      (value, segment) =>
        value && typeof value === "object"
          ? (value as Record<string, unknown>)[segment]
          : undefined,
      resource,
    );
}

describe("locale resources", () => {
  it("keeps the duration column label as a string", () => {
    expect(en.duration).toBeTypeOf("string");
    expect(zh.duration).toBeTypeOf("string");
  });

  it("keeps English and Chinese keys identical", () => {
    expect(leafKeys(zh).sort()).toEqual(leafKeys(en).sort());
  });

  it("keeps interpolation variables identical", () => {
    expect(placeholders(zh)).toEqual(placeholders(en));
  });

  it("matches literal translation calls to scalar or object resources", () => {
    const failures: string[] = [];
    const callPattern = /\bt\(\s*["']([^"']+)["']([\s\S]*?)\)/g;

    for (const [file, source] of Object.entries(sourceFiles)) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;

      for (const match of source.matchAll(callPattern)) {
        const [, key, options] = match;
        const expectsObject = /returnObjects\s*:\s*true/.test(options);

        for (const [locale, resource] of [
          ["en", en],
          ["zh", zh],
        ] as const) {
          const value = resourceValue(resource, key);
          const valid = expectsObject
            ? value !== null && typeof value === "object"
            : typeof value === "string";
          if (!valid) {
            failures.push(
              `${file}: ${locale}.${key} must be ${expectsObject ? "an object" : "a string"}`,
            );
          }
        }
      }
    }

    expect(failures).toEqual([]);
  });
});
