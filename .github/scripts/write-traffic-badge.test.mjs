import assert from "node:assert/strict";
import test from "node:test";
import { trafficBadge } from "./write-traffic-badge.mjs";

test("publishes the total number of clones, including a genuine zero", () => {
  assert.equal(trafficBadge({ count: 1238, uniques: 313 }).message, "1238");
  assert.equal(trafficBadge({ count: 0 }).message, "0");
  assert.equal(trafficBadge({ count: 1238 }).label, "clones/14 days");
});

test("rejects missing or malformed counts instead of publishing zero", () => {
  for (const data of [
    null,
    {},
    { count: -1 },
    { count: "1238" },
    { count: 1.5 },
  ]) {
    assert.throws(() => trafficBadge(data), /invalid clone count/);
  }
});
