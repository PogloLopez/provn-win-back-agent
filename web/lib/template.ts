// Client-side preview of an email template: splits text into literal and placeholder parts,
// so values can be highlighted. The server renders the real email with Jinja2.

export type Part = { kind: "text"; text: string } | { kind: "value"; name: string; text: string };

const PLACEHOLDER = /{{\s*(\w+)\s*}}/g;

export function renderParts(template: string, values: Record<string, string>): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const match of template.matchAll(PLACEHOLDER)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ kind: "text", text: template.slice(last, index) });
    const name = match[1];
    parts.push({ kind: "value", name, text: values[name] ?? `{{${name}}}` });
    last = index + match[0].length;
  }
  if (last < template.length) parts.push({ kind: "text", text: template.slice(last) });
  return parts;
}

/** What each placeholder renders to for a set of offers, from the edit options. */
export function placeholderValues(
  base: Record<string, string>,
  phrases: Record<string, Record<string, string>>,
  offers: { type: string; value: number }[],
): Record<string, string> {
  const values = { ...base };
  for (const offer of offers) {
    const phrase = phrases[offer.type]?.[String(offer.value)];
    if (phrase) values[offer.type] = phrase;
  }
  return values;
}
