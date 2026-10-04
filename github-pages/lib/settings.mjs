import assert from "node:assert/strict";

export function siteSettings(env = process.env) {
  const base = env.DOCS_BASE || "/AxonX/";
  assert(
    /^\/(?:[\w-]+\/)*$/.test(base),
    "DOCS_BASE must be a slash-delimited mount path",
  );
  const origin = new URL(env.DOCS_SITE_URL || "https://flowllm-ai.github.io");
  assert(
    ["http:", "https:"].includes(origin.protocol),
    "DOCS_SITE_URL must use HTTP(S)",
  );
  assert(
    origin.pathname === "/" &&
      !origin.search &&
      !origin.hash &&
      !origin.username &&
      !origin.password,
    "DOCS_SITE_URL must contain only a site origin",
  );
  return { base, siteUrl: origin.origin };
}
