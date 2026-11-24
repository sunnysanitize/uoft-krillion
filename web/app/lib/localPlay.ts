import type { AttemptResult, LocalPlay } from "./api";

const FILLER = new Set(["the", "of", "and", "a", "at", "uoft", "u", "t"]);
const GENERIC = new Set([
  "library", "hall", "building", "centre", "center", "college", "street", "avenue", "ave", "road",
  "station", "house", "residence", "school", "faculty", "university", "laboratory", "laboratories", "lab", "labs",
]);

/** Mirrors domain/matching.py, including short codes, generic suffixes and typo suggestions. */
export function normalize(text: string): string {
  return text.normalize("NFKD").replace(/[^\x00-\x7F]/g, "").toLowerCase()
    .replace(/&/g, " and ").replace(/'/g, "").replace(/\bst\b\.?/g, "saint")
    .replace(/[^a-z0-9]+/g, " ").split(/\s+/).filter((word) => word && !FILLER.has(word)).join(" ");
}

function stripGeneric(key: string): string {
  const words = key.split(" ");
  while (words.length > 1 && GENERIC.has(words[words.length - 1])) words.pop();
  return words.join(" ");
}

function aliasIndex(groups: string[][]): Map<string, string> {
  const index = new Map<string, string>();
  for (const names of groups) for (const name of names) {
    const key = normalize(name);
    if (!index.has(key)) index.set(key, names[0]);
  }
  return index;
}

// SequenceMatcher's matching-block ratio, with the same argument order as get_close_matches.
// Names are shorter than its 200-character autojunk threshold.
function similarity(candidate: string, guess: string): number {
  function matches(a0: number, a1: number, b0: number, b1: number): number {
    let best = 0, startA = a0, startB = b0;
    let previous = new Map<number, number>();
    for (let i = a0; i < a1; i++) {
      const current = new Map<number, number>();
      for (let j = b0; j < b1; j++) if (candidate[i] === guess[j]) {
        const length = (previous.get(j - 1) ?? 0) + 1;
        current.set(j, length);
        if (length > best) { best = length; startA = i - length + 1; startB = j - length + 1; }
      }
      previous = current;
    }
    if (!best) return 0;
    return best + matches(a0, startA, b0, startB) + matches(startA + best, a1, startB + best, b1);
  }
  const total = candidate.length + guess.length;
  return total ? 2 * matches(0, candidate.length, 0, guess.length) / total : 1;
}

function closest(key: string, index: Map<string, string>, cutoff: number): string | null {
  let best: string | null = null, ratio = cutoff;
  for (const alias of index.keys()) {
    const score = similarity(alias, key);
    if (score >= ratio && (score > ratio || best === null || alias > best)) {
      best = alias;
      ratio = score;
    }
  }
  return best === null ? null : index.get(best)!;
}

function match(groups: string[][], raw: string, fuzzy = true): string | null {
  let key = normalize(raw);
  if (!key) return null;
  const index = aliasIndex(groups);
  if (index.has(key)) return index.get(key)!;
  key = stripGeneric(key);
  if (index.has(key)) return index.get(key)!;
  if (key.length >= 4 && !key.split(" ").every((word) => GENERIC.has(word))) {
    const hits = new Set([...index].filter(([alias]) => alias.startsWith(key + " ")).map(([, name]) => name));
    if (hits.size === 1) return [...hits][0];
  }
  return fuzzy && key.length >= 5 ? closest(key, index, 0.85) : null;
}

/** Fully synchronous: neither matching nor the scored animation waits on a request. */
export function localAttempt(play: LocalPlay, raw: string, force = false): AttemptResult {
  const groups = play.answers.map((answer) => answer.names);
  const known = [...groups, ...play.decoys.map((name) => [name])];
  const answer = match(groups, raw);
  const recognized = match(known, raw, false) !== null;
  if (!force && (!recognized || answer === null)) {
    let suggestion: string | null = null;
    const key = stripGeneric(normalize(raw));
    if (!recognized && key.length >= 3) {
      const index = aliasIndex(known);
      for (const [alias, name] of [...index]) if (!index.has(stripGeneric(alias))) index.set(stripGeneric(alias), name);
      suggestion = closest(key, index, 0.7);
    }
    return { accepted: false, check: { recognized, correct: false, suggestion } };
  }
  const row = play.answers.find((entry) => entry.names[0] === answer);
  return {
    accepted: true,
    result: {
      valid: !!row, answer: row?.names[0] ?? null, points: row?.points ?? 0,
      share_pct: row?.share_pct ?? null, rarity: row?.rarity ?? null, golden: row?.golden ?? false,
      golden_answer: play.golden_answer, top: play.top, deep_cuts: play.deep_cuts,
      players: play.players, valid_answers: play.valid_answers,
    },
  };
}
