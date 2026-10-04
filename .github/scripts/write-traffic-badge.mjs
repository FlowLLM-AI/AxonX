import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { pathToFileURL } from "node:url";

export function trafficBadge(data) {
  if (!Number.isSafeInteger(data?.count) || data.count < 0) {
    throw new Error("GitHub returned an invalid clone count");
  }
  return {
    schemaVersion: 1,
    label: "clones/14 days",
    message: String(data.count),
    color: "blue",
    cacheSeconds: 3600,
  };
}

async function main() {
  const output = process.argv[2];
  if (!output) throw new Error("Usage: node write-traffic-badge.mjs OUTPUT");
  const token = process.env.AXONX_TRAFFIC_TOKEN;
  let badge;
  if (token) {
    const response = await fetch(
      "https://api.github.com/repos/FlowLLM-AI/AxonX/traffic/clones",
      {
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${token}`,
          "X-GitHub-Api-Version": "2026-03-10",
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (!response.ok) {
      throw new Error(`GitHub traffic request failed: HTTP ${response.status}`);
    }
    badge = trafficBadge(await response.json());
  } else {
    badge = {
      schemaVersion: 1,
      label: "clones/14 days",
      message: "not configured",
      color: "lightgrey",
    };
  }
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, JSON.stringify(badge) + "\n");
  console.log(`Clone badge: ${badge.message}`);
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
