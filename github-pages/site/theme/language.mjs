/** @typedef {"en" | "zh"} Language */

/** @returns {Language | undefined} */
function supportedLanguage(value) {
  return value === "en" || value === "zh" ? value : undefined;
}

/** Explicit URLs take precedence over preferences, as in Studio. */
export function initialLanguage({ relativePath, search, saved, browser }) {
  return (
    supportedLanguage(new URLSearchParams(search).get("lang")) ||
    supportedLanguage(relativePath.split("/")[0]) ||
    supportedLanguage(saved) ||
    (browser?.toLowerCase().startsWith("zh") ? "zh" : "en")
  );
}

/** Build a language route while preserving the document, query, and anchor. */
export function languageRoute(relativePath, language, search = "", hash = "") {
  const page = relativePath
    .replace(/^(en|zh)\//, "")
    .replace(/(^|\/)index\.md$/, "$1")
    .replace(/\.md$/, "");
  const params = new URLSearchParams(search);
  if (params.has("lang")) params.set("lang", language);
  const query = params.toString();
  return `/${language}/${page}${query ? `?${query}` : ""}${hash}`;
}
