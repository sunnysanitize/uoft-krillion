import type { GuessResult, Rarity } from "./api";

/** Visual tier of a single answer. Drives colour everywhere a result is shown. */
export type Tone = "golden" | "deepcut" | "rare" | "uncommon" | "common" | "miss";

const TONE_OF: Record<Rarity, Tone> = {
  "One in a Krillion": "golden",
  "Deep Cut": "deepcut",
  Rare: "rare",
  Uncommon: "uncommon",
  Common: "common",
};

export const toneOfRarity = (rarity: Rarity): Tone => TONE_OF[rarity] ?? "common";

export function toneOf(r: GuessResult): Tone {
  if (r.golden) return "golden";
  if (!r.valid || !r.rarity) return "miss";
  return TONE_OF[r.rarity] ?? "common";
}

// Full class strings so Tailwind can see them at build time.
export const TONE_TEXT: Record<Tone, string> = {
  golden: "text-gold",
  deepcut: "text-deep",
  rare: "text-rare",
  uncommon: "text-perch",
  common: "text-alewife",
  miss: "text-slate",
};

export const TONE_BG: Record<Tone, string> = {
  golden: "bg-gold",
  deepcut: "bg-deep",
  rare: "bg-rare",
  uncommon: "bg-perch",
  common: "bg-alewife",
  miss: "bg-slate",
};

export const TONE_LABEL: Record<Tone, string> = {
  golden: "One in a Krillion",
  deepcut: "Deep Cut",
  rare: "Rare",
  uncommon: "Uncommon",
  common: "Common",
  miss: "Out of air",
};

// How far each tier sinks you, in metres. It climbs steeply so the deep tiers really plunge:
// a Deep Cut goes far deeper than a Rare, and One in a Krillion further still. Points are separate.
const DROP_M: Record<Tone, number> = { miss: 0, common: 100, uncommon: 300, rare: 700, deepcut: 1500, golden: 2500 };
export const dropOf = (r: GuessResult) => DROP_M[toneOf(r)];

/** The creature each tier lands you, with its sprite in /public/fish. */
export const CREATURE: Record<Tone, { name: string; src: string } | null> = {
  common: { name: "Lake Ontario Alewife", src: "/fish/alewife.png" },
  uncommon: { name: "Toronto Perch", src: "/fish/perch.png" },
  rare: { name: "Lake Sturgeon", src: "/fish/sturgeon.png" },
  deepcut: { name: "Abyssal Anglerfish", src: "/fish/anglerfish.png" },
  golden: { name: "Legendary Varsity Krill", src: "/fish/krill.png" },
  miss: null,
};

export const TONE_LINE: Record<Tone, string> = {
  golden: "The one answer hidden at the bottom.",
  deepcut: "Deep in the stacks. Nice.",
  rare: "You have been around campus.",
  uncommon: "Plenty of company on this one.",
  common: "The answer everyone in Sid Smith blurts out.",
  miss: "Not on the list.",
};

/** One line per depth zone for the results legend. */
export const ZONE_LINE: Record<string, string> = {
  "Philosopher's Walk Shallows": "Still in sight of the shore.",
  "Sid Smith Drop-off": "Past the first-year crowds.",
  "Bahen Trench": "Where the all-nighters live.",
  "Robarts Abyss": "Down in the concrete peacock. Respect.",
  "The Steam Tunnels": "Nobody comes down here.",
};

/** Best possible day: the One in a Krillion answer on every prompt (server: GOLDEN_POINTS = 100). */
export const maxScore = (prompts: number) => prompts * 100;

// The share grid goes to group chats, where emoji are the lingua franca.
const SHARE_GLYPH: Record<Tone, string> = {
  golden: "🦐",
  deepcut: "🟪",
  rare: "🟥",
  uncommon: "🟩",
  common: "⬜",
  miss: "⬛",
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

const ADJECTIVES = ["Swift", "Quiet", "Brave", "Sleepy", "Lucky", "Curious", "Salty", "Sly", "Bold", "Misty", "Gloomy", "Zippy"];
const CREATURES = ["Lanternfish", "Anglerfish", "Octopus", "Squid", "Seahorse", "Narwhal", "Otter", "Nautilus", "Jellyfish", "Eel", "Manta", "Goose"];

/** A random leaderboard name, picked once and kept, since players don't type one. */
export function diverName(): string {
  const pick = (list: string[]) => list[Math.floor(Math.random() * list.length)];
  const name = `${pick(ADJECTIVES)} ${pick(CREATURES)}`;
  persist("rb:nickname", name);
  return name;
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
