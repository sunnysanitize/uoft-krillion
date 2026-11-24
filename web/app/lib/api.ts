export type Prompt = {
  id: string;
  text: string;
  hint: string;
  /** Loaded with the daily set; optional while an older backend is deploying. */
  play?: LocalPlay;
};

export type LocalAnswer = {
  names: string[];
  points: number;
  share_pct: number;
  rarity: Rarity;
  golden: boolean;
};

export type LocalPlay = {
  answers: LocalAnswer[];
  decoys: string[];
  golden_answer: string;
  top: { answer: string; pct: number }[];
  deep_cuts: string[];
  players: number;
  valid_answers: number;
};

/** Whether a typed answer is one the game knows, whether it's right, and else a "did you mean". */
export type CheckResult = { recognized: boolean; correct: boolean; suggestion: string | null };

export type AttemptResult =
  | { accepted: true; result: GuessResult }
  | { accepted: false; check: CheckResult };

export type Daily = {
  day: string;
  number: number;
  time_limit: number;
  meters_per_point: number;
  zones: { start: number; name: string }[];
  prompts: Prompt[];
};

/** Rarity tiers from the server, most common first. */
export type Rarity = "Common" | "Uncommon" | "Rare" | "Deep Cut" | "One in a Krillion";

export type GuessResult = {
  valid: boolean;
  answer: string | null;
  points: number;
  share_pct: number | null;
  rarity: Rarity | null;
  golden: boolean;
  golden_answer: string;
  top: { answer: string; pct: number }[];
  deep_cuts: string[];
  players: number;
  valid_answers: number;
  raw?: string;
  /** Local persistence only: false until the background guess has been recorded. */
  synced?: boolean;
};

/** One row of a prompt's full answer list, shown after you've played it. */
export type AnswerRow = { answer: string; pct: number; points: number; rarity: Rarity; golden: boolean; yours: boolean };

export type FinishResult = { score: number; percentile: number; players: number };

export type Leaderboard = {
  players: { nickname: string; score: number }[];
};

class ApiError extends Error {
  constructor(path: string, readonly status: number) {
    super(`${path} failed (${status})`);
  }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(path, res.status);
  return res.json();
}

export const api = {
  daily: () => call<Daily>("daily"),
  check: (prompt_id: string, answer: string) => call<CheckResult>("check", { prompt_id, answer }),
  guess: (player_id: string, prompt_id: string, answer: string) =>
    call<GuessResult>("guess", { player_id, prompt_id, answer }),
  attempt: async (player_id: string, prompt_id: string, answer: string): Promise<AttemptResult> => {
    try {
      return await call<AttemptResult>("attempt", { player_id, prompt_id, answer });
    } catch (error) {
      // Frontend and backend deploy separately. Support the old API during rollout.
      if (!(error instanceof ApiError) || (error.status !== 404 && error.status !== 405)) throw error;
      const check = await api.check(prompt_id, answer);
      if (!check.correct) return { accepted: false, check };
      return { accepted: true, result: await api.guess(player_id, prompt_id, answer) };
    }
  },
  answers: (player_id: string, prompt_id: string) =>
    call<{ answers: AnswerRow[] }>("answers", { player_id, prompt_id }).then((r) => r.answers),
  finish: (player_id: string, nickname: string) => call<FinishResult>("finish", { player_id, nickname }),
  leaderboard: () => call<Leaderboard>("leaderboard"),
  /** Only exists when the backend runs with DEV_RESET=1 (docker compose sets it). */
  devReset: (player_id: string) => call<{ ok: boolean }>("dev/reset", { player_id }),
};
