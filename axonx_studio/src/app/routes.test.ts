import { describe, expect, it } from "vitest";
import { defaultRoute, parseHash, routeHash } from "./routes";

describe("application routes", () => {
  it("parses a machine resource route", () => {
    expect(parseHash("#10.0.0.1:1024/raw/files/tushare%2Fdaily")).toEqual({
      machineId: "10.0.0.1:1024",
      route: { section: "raw", view: "files", resource: "tushare/daily" },
    });
  });

  it("uses a compact machine address with a readable port", () => {
    const route = {
      section: "raw" as const,
      view: "files",
      resource: "tushare",
    };
    expect(routeHash("11.160.132.45:1024", route)).toBe(
      "#11.160.132.45:1024/raw/files/tushare",
    );
    expect(parseHash(routeHash("11.160.132.45:1024", route))).toEqual({
      machineId: "11.160.132.45:1024",
      route,
    });
    expect(
      parseHash(routeHash("https://axonx.example.com:443", route)),
    ).toEqual({
      machineId: "https://axonx.example.com:443",
      route,
    });
  });

  it("opens home by default", () => {
    expect(parseHash("")).toEqual({
      machineId: "local",
      route: { section: "home", view: "overview", resource: undefined },
    });
  });

  it("fills in the view before an encoded resource", () => {
    const hash = routeHash("[::1]:1024", {
      section: "raw",
      resource: "tushare/daily#1",
    });
    expect(parseHash(hash)).toEqual({
      machineId: "[::1]:1024",
      route: { section: "raw", view: "files", resource: "tushare/daily#1" },
    });
    expect(routeHash("local", { section: "home" })).toBe(
      "#local/home/overview",
    );
  });

  it("falls back to home for unknown routes and retains home links", () => {
    expect(parseHash("#local/unknown")).toEqual({
      machineId: "local",
      route: { section: "home", view: "overview", resource: undefined },
    });
    expect(parseHash("#local/home/overview").route).toEqual({
      section: "home",
      view: "overview",
      resource: undefined,
    });
  });

  it("round-trips encoded routes", () => {
    const route = {
      section: "runtime" as const,
      view: "task",
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
    expect(defaultRoute("agent")).toEqual({
      section: "agent",
      view: "new",
      resource: undefined,
    });
    expect(
      parseHash(
        routeHash("local", {
          section: "runtime",
          view: "task",
          resource: "predict#123",
        }),
      ).route,
    ).toEqual({
      section: "runtime",
      view: "task",
      resource: "predict#123",
    });
  });

  it("round-trips agent session and task routes", () => {
    expect(
      parseHash(
        routeHash("local", {
          section: "agent",
          view: "chat",
          resource: "3ca32703-42fe-4c8f-990a-67ef49e0fe12",
        }),
      ).route,
    ).toEqual({
      section: "agent",
      view: "chat",
      resource: "3ca32703-42fe-4c8f-990a-67ef49e0fe12",
    });
    expect(parseHash("#local/agent/task/predict%23123").route).toEqual({
      section: "agent",
      view: "task",
      resource: "predict#123",
    });
  });

  it("keeps strategy comparison on its own route", () => {
    const route = { section: "compare" as const, view: "strategies" };
    expect(parseHash(routeHash("11.160.132.45:1024", route))).toEqual({
      machineId: "11.160.132.45:1024",
      route: { ...route, resource: undefined },
    });
  });
});
