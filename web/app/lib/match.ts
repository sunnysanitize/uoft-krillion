/**
 * Client-side spelling help over the prompt's suggestion list. This never decides
 * whether an answer is valid (the list includes decoys); the server does that.
 */

export const norm = (s: string) =>
  s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/'/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cur = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
  }
  return row[b.length];
}

/** A near-miss spelling of exactly one suggestion, e.g. "will byer" -> "Will Byers". */
export function typoOf(input: string, suggestions: string[]): string | null {
  const key = norm(input);
  if (key.length < 4) return null;
  let best: { s: string; score: number } | null = null;
  for (const s of suggestions) {
    const n = norm(s);
    if (n === key) return null; // already spelled right
    const score = 1 - distance(key, n) / Math.max(key.length, n.length);
    if (!best || score > best.score) best = { s, score };
  }
  return best && best.score >= 0.75 ? best.s : null;
}

/** Up to `limit` suggestions for what's typed: word-prefix matches first, then substring matches. */
export function complete(input: string, suggestions: string[], limit = 5): string[] {
  const key = norm(input);
  if (key.length < 2) return [];
  const starts: string[] = [];
  const contains: string[] = [];
  for (const s of suggestions) {
    const n = norm(s);
    if (n === key) continue;
    if (n.startsWith(key) || n.includes(` ${key}`)) starts.push(s);
    else if (n.includes(key)) contains.push(s);
  }
  return [...starts, ...contains].slice(0, limit);
}
