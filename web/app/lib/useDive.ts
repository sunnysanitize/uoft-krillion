"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Daily, FinishResult, GuessResult, Leaderboard } from "./api";
import { diverName, dropOf, persist, playerId, storage, toneOf, zoneAt, type Tone } from "./game";

export type Phase = "loading" | "intro" | "play" | "flash" | "done" | "error";

// How long the camera takes to sink after an answer: short for every tier, a touch longer the deeper.
export const SINK_MS = 1800;
const SINK: Record<Tone, number> = { miss: 600, common: 1200, uncommon: 1400, rare: 1700, deepcut: 2100, golden: 2500 };
export const sinkMs = (r: GuessResult) => SINK[toneOf(r)];

// How the drop feels. A Common is an awkward little plop: it hesitates, bobs up, drops a touch too
// far, and settles back. From Uncommon up the camera builds speed as it falls, exponentially harder
// the higher the tier, then brakes and glides into its new depth rather than stopping dead.
export const SINK_EASE = "cubic-bezier(.45,.05,.2,1)";
const PLUNGE: Partial<Record<Tone, string>> = {
  common: "cubic-bezier(.6,-0.6,.35,1.7)",
  uncommon: "cubic-bezier(.55,0,.3,1)",
  rare: "cubic-bezier(.7,0,.25,1)",
  deepcut: "cubic-bezier(.8,0,.2,1)",
  golden: "cubic-bezier(.87,0,.15,1)",
};
export const sinkEase = (r: GuessResult) => PLUNGE[toneOf(r)] ?? SINK_EASE;

// The verdict and creature show the moment you answer, while the drop plays behind them; One in a
// Krillion lingers. The beat lasts at least until the drop has landed, then the next clock starts.
export const verdictMs = (r: GuessResult) => Math.max(sinkMs(r) + 900, r.golden ? 3000 : 2600);
export const flashMs = verdictMs;

type Saved = {
  results: GuessResult[];
  startedAt: number | null;
  nickname: string;
};

/** All game state and server calls for one day's dive. Screens stay presentational. */
export function useDive() {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [saved, setSaved] = useState<Saved>({ results: [], startedAt: null, nickname: "" });
  const [now, setNow] = useState(() => Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [finish, setFinish] = useState<FinishResult | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);

  const idx = saved.results.length;
  const prompt = daily?.prompts[idx];
  const mpp = daily?.meters_per_point ?? 10;
  const score = saved.results.reduce((s, r) => s + r.points, 0);
  const depth = saved.results.reduce((d, r) => d + dropOf(r), 0);
  const zone = daily ? zoneAt(daily.zones, depth) : null;
  const saveKey = daily ? `rb:dive:${daily.day}` : null;

  const update = useCallback(
    (next: Saved) => {
      setSaved(next);
      if (saveKey) persist(saveKey, next);
    },
    [saveKey],
  );

  useEffect(() => {
    api
      .daily()
      .then((d) => {
        setDaily(d);
        const s = storage<Saved>(`rb:dive:${d.day}`, {
          results: [],
          startedAt: null,
          nickname: storage("rb:nickname", "") || diverName(),
        });
        setSaved(s);
        if (s.results.length >= d.prompts.length) setPhase("done");
        else if (s.startedAt) setPhase("play"); // refreshing doesn't reset the clock
        else if (s.results.length > 0) {
          // Left between prompts: pick up at the next one with a fresh clock.
          const resumed = { ...s, startedAt: Date.now() };
          setSaved(resumed);
          persist(`rb:dive:${d.day}`, resumed);
          setPhase("play");
        } else setPhase("intro");
      })
      .catch(() => setPhase("error"));
  }, []);

  const submit = useCallback(
    async (text: string) => {
      if (!daily || !prompt || submitting) return;
      setSubmitting(true);
      try {
        const r = await api.guess(playerId(), prompt.id, text);
        const result = { ...r, raw: text };
        const next = { ...saved, results: [...saved.results, result], startedAt: null };
        update(next);
        // Flash the verdict, then the next prompt (its clock starts now) or the results.
        setPhase("flash");
        setTimeout(() => {
          if (next.results.length >= daily.prompts.length) return setPhase("done");
          const t = Date.now();
          setNow(t);
          update({ ...next, startedAt: t });
          setPhase("play");
        }, flashMs(result));
      } catch {
        setPhase("error");
      } finally {
        setSubmitting(false);
      }
    },
    [daily, prompt, saved, submitting, update],
  );

  const limitMs = (daily?.time_limit ?? 20) * 1000;
  const remaining = saved.startedAt ? Math.max(0, limitMs - (now - saved.startedAt)) : limitMs;

  useEffect(() => {
    if (phase !== "play") return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [phase, idx]);

  const [sonarLost, setSonarLost] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // Post the finish, then read the board (so it includes us). If posting fails, still show the board.
  useEffect(() => {
    if (phase !== "done" || !daily) return;
    const name = saved.nickname.trim() || "anon goose";
    setSonarLost(false);
    api
      .finish(playerId(), name)
      .then(setFinish)
      .catch(() => setSonarLost(true))
      .finally(() =>
        api
          .leaderboard()
          .then(setBoard)
          .catch(() => setSonarLost(true)),
      );
  }, [phase, daily, saved.nickname, attempt]);

  const retrySonar = () => setAttempt((n) => n + 1);

  function begin() {
    if (!daily) return;
    persist("rb:nickname", saved.nickname);
    const t = Date.now();
    setNow(t);
    update({ ...saved, startedAt: t });
    setPhase("play");
  }


  return {
    daily,
    phase,
    results: saved.results,
    nickname: saved.nickname,
    idx,
    prompt,
    mpp,
    score,
    depth,
    zone,
    remaining,
    limitMs,
    submitting,
    finish,
    board,
    sonarLost,
    retrySonar,
    submit,
    begin,
  };
}

export type Dive = ReturnType<typeof useDive>;
