// Transform document URLs while leaving fenced examples unchanged.
export function mapLinks(content, resolve) {
  const transform = (text) =>
    text
      .replace(
        /(!?\[[^\]\n]*\]\()([^\s)]+)([^)]*\))/g,
        (_, start, href, end) =>
          `${start}${resolve(href, start.startsWith("!"))}${end}`,
      )
      .replace(
        /(<(?:a|img)\b[^>]*?\b(?:href|src)=)(["'])(.*?)\2/gi,
        (_, start, quote, href) =>
          `${start}${quote}${resolve(href, /^<img\b/i.test(start), true)}${quote}`,
      );

  let fence;
  let prose = "";
  let result = "";
  for (const line of content.split(/(?<=\n)/)) {
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)/);
    if (fence) {
      if (
        marker &&
        marker[1][0] === fence[0] &&
        marker[1].length >= fence.length &&
        !marker[2].trim()
      )
        fence = undefined;
      result += line;
    } else if (marker) {
      result += transform(prose) + line;
      prose = "";
      fence = marker[1];
    } else {
      prose += line;
    }
  }
  return result + transform(prose);
}
