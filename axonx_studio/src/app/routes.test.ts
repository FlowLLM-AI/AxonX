import { describe, expect, it } from "vitest";
import { defaultRoute, parseHash, routeHash } from "./routes";

describe("application routes", () => {
  it("parses a machine-scoped resource route", () => {
    expect(parseHash("#m/10.0.0.1%3A1024/raw/files/tushare%2Fdaily")).toEqual({
      machineId: "10.0.0.1:1024",
      route: { section: "raw", view: "files", resource: "tushare/daily" },
    });
  });

  it("falls back to task management for unknown routes and retains home links", () => {
    expect(parseHash("#m/local/unknown")).toEqual({
      machineId: "local",
      route: { section: "runtime", view: "tasks", resource: undefined },
    });
    expect(parseHash("#m/local/home/overview").route).toEqual({
      section: "home",
      view: "overview",
      resource: undefined,
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
    expect(defaultRoute("train")).toEqual({
      section: "train",
      view: "runs",
      resource: undefined,
    });
    expect(
      parseHash(
        routeHash("local", {
          section: "lineage",
          view: "runs",
          resource: "predict#123",
        }),
      ).route.resource,
    ).toBe("predict#123");
  });

  it("keeps strategy comparison on its own route", () => {
    const route = { section: "compare" as const, view: "strategies" };
    expect(parseHash(routeHash("11.160.132.45:1024", route))).toEqual({
      machineId: "11.160.132.45:1024",
      route: { ...route, resource: undefined },
    });
  });
});
