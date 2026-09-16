import { describe, expect, it } from "vitest";
import { defaultRoute, parseHash, routeHash } from "./routes";

describe("application routes", () => {
  it("parses a machine-scoped resource route", () => {
    expect(parseHash("#m/10.0.0.1%3A1024/raw/files/tushare%2Fdaily")).toEqual({
      machineId: "10.0.0.1:1024",
      route: { section: "raw", view: "files", resource: "tushare/daily" },
    });
  });

  it("falls back to the home route for unknown sections", () => {
    expect(parseHash("#m/local/unknown")).toEqual({
      machineId: "local",
      route: { section: "home", view: "overview", resource: undefined },
    });
  });

  it("round-trips encoded routes", () => {
    const route = {
      section: "runtime" as const,
      view: "tasks",
      resource: "task#20260916",
    };
    expect(parseHash(routeHash("local", route))).toEqual({
      machineId: "local",
      route,
    });
  });

  it("provides section defaults", () => {
    expect(defaultRoute("raw")).toEqual({
      section: "raw",
      view: "files",
      resource: "tushare",
    });
    expect(defaultRoute("training")).toEqual({
      section: "training",
      view: "runs",
      resource: undefined,
    });
  });
});
