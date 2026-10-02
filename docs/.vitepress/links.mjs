// Transform document URLs while leaving fenced examples unchanged.
export function mapLinks(content, resolve) {
  return content
    .split(/(^```[^\n]*\n[\s\S]*?^```[^\n]*$|^~~~[^\n]*\n[\s\S]*?^~~~[^\n]*$)/m)
    .map((part, index) =>
      index % 2
        ? part
        : part
            .replace(
              /(!?\[[^\]\n]*\]\()([^\s)]+)([^)]*\))/g,
              (_, start, href, end) =>
                `${start}${resolve(href, start.startsWith("!"))}${end}`,
            )
            .replace(
              /(<(?:a|img)\b[^>]*?\b(?:href|src)=)(["'])(.*?)\2/gi,
              (_, start, quote, href) =>
                `${start}${quote}${resolve(href, /^<img\b/i.test(start), true)}${quote}`,
            ),
    )
    .join("");
}
