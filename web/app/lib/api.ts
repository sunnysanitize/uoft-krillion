export type Prompt = { id: string; text: string; hint: string };

export type Daily = {
  day: string;
  number: number;
  time_limit: number;
  meters_per_point: number;
  zones: { start: number; name: string }[];
  colleges: string[];
  prompts: Prompt[];
};

export type GuessResult = {
  valid: boolean;
  answer: string | null;
  points: number;
  share_pct: number | null;
  rarity: "Legendary" | "Rare" | "Uncommon" | "Common" | "Basic" | null;
  golden: boolean;
  golden_answer: string;
  top: { answer: string; pct: number }[];
  deep_cuts: string[];
  players: number;
  valid_answers: number;
  raw?: string;
};

export type FinishResult = { score: number; percentile: number; players: number };

export type Leaderboard = {
  players: { nickname: string; college: string | null; score: number }[];
  colleges: { college: string; avg: number; n: number }[];
};

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

export const api = {
  daily: () => call<Daily>("daily"),
  guess: (player_id: string, prompt_id: string, answer: string) =>
    call<GuessResult>("guess", { player_id, prompt_id, answer }),
  finish: (player_id: string, nickname: string, college: string | null) =>
    call<FinishResult>("finish", { player_id, nickname, college }),
  leaderboard: () => call<Leaderboard>("leaderboard"),
};
