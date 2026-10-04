// Ignore shell comments and Markdown examples inside fenced code blocks.
export function documentTitle(content) {
  let fence;
  for (const line of content.split(/\r?\n/)) {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fence) {
      if (
        marker &&
        marker[1][0] === fence[0] &&
        marker[1].length >= fence.length &&
        !marker[2].trim()
      )
        fence = undefined;
      continue;
    }
    if (marker) {
      fence = marker[1];
      continue;
    }
    const heading = line.match(/^ {0,3}#\s+(.+?)(?:\s+#+)?\s*$/);
    if (heading) return heading[1];
  }
}

// The project README starts with a logo instead of an H1. Give its imported
// page an explicit title without changing the canonical README.
export const importedTitles = {
  "getting-started/overview": { en: "AxonX overview", zh: "AxonX 项目概览" },
};
