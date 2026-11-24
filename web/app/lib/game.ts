import type { GuessResult } from "./api";

/** Visual tier of a single answer. Drives colour everywhere a result is shown. */
export type Tone = "golden" | "legendary" | "rare" | "uncommon" | "common" | "basic" | "miss";

export function toneOf(r: GuessResult): Tone {
  if (r.golden) return "golden";
  if (!r.valid || !r.rarity) return "miss";
  return r.rarity.toLowerCase() as Tone;
}

// Full class strings so Tailwind can see them at build time.
export const TONE_TEXT: Record<Tone, string> = {
  golden: "text-gold",
  legendary: "text-gold",
  rare: "text-sonar",
  uncommon: "text-foam",
  common: "text-mist",
  basic: "text-slate",
  miss: "text-coral",
};

export const TONE_BG: Record<Tone, string> = {
  golden: "bg-gold",
  legendary: "bg-gold",
  rare: "bg-sonar",
  uncommon: "bg-foam",
  common: "bg-mist",
  basic: "bg-slate",
  miss: "bg-coral",
};

// Rarity tiers in campus terms, shallowest to deepest.
export const TONE_LABEL: Record<Tone, string> = {
  golden: "Golden Krill",
  legendary: "Tenured",
  rare: "Grad student",
  uncommon: "Upper-year",
  common: "Commuter",
  basic: "Frosh",
  miss: "Nothing landed",
};

export const TONE_LINE: Record<Tone, string> = {
  golden: "The one answer hidden at the bottom. Huge bonus.",
  legendary: "Almost nobody thought of that.",
  rare: "Deep in the stacks. Nice.",
  uncommon: "You have been around campus.",
  common: "Plenty of company on this one.",
  basic: "The answer everyone in Sid Smith blurts out.",
  miss: "Not on the list.",
};

/** One line per depth zone for the results legend. */
export const ZONE_LINE: Record<string, string> = {
  "Philosopher's Walk Shallows": "Still in sight of the shore.",
  "Sid Smith Drop-off": "Past the first-year crowds.",
  "Bahen Trench": "Where the all-nighters live.",
  "Robarts Abyss": "Down in the concrete peacock. Respect.",
  "The Steam Tunnels": "Nobody comes down here. Legendary.",
};

/** Best possible day: every prompt at full rarity plus its Golden Krill (server: 100 + 100 per prompt). */
export const maxScore = (prompts: number) => prompts * 200;

// The share grid goes to group chats, where emoji are the lingua franca.
const SHARE_GLYPH: Record<Tone, string> = {
  golden: "🦐",
  legendary: "🟨",
  rare: "🟦",
  uncommon: "🟩",
  common: "⬜",
  basic: "⬛",
  miss: "🟥",
};

export const shareGlyph = (r: GuessResult) => SHARE_GLYPH[toneOf(r)];

export const meters = (n: number) => `${n.toLocaleString("en-CA")} m`;

export type Zone = { start: number; name: string };

export const zoneAt = (zones: Zone[], depth: number) =>
  [...zones].reverse().find((z) => depth >= z.start) ?? zones[0];

export function storage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function persist(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

export function playerId(): string {
  let id = storage<string | null>("rb:player", null);
  if (!id) {
    id = crypto.randomUUID();
    persist("rb:player", id);
  }
  return id;
}

/** Milliseconds until the next dive, which resets at midnight Toronto time. */
export function msToNextDive(now = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto",
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  const elapsed = get("hour") * 3600 + get("minute") * 60 + get("second");
  return (86400 - elapsed) * 1000;
}

export function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}
