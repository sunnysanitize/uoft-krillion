"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, CheckResult, Daily, FinishResult, GuessResult, Leaderboard } from "./api";
import { diverName, dropOf, persist, playerId, storage, toneOf, zoneAt, type Tone } from "./game";
import { localAttempt } from "./localPlay";

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
  const savedRef = useRef(saved);
  const [now, setNow] = useState(() => Date.now());
  const [submitting, setSubmitting] = useState(false);
  const submission = useRef(false);
  const [finish, setFinish] = useState<FinishResult | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [sonarLost, setSonarLost] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const syncing = useRef(new Set<string>());
  const failed = useRef(new Set<string>());

  const idx = saved.results.length;
  const prompt = daily?.prompts[idx];
  const mpp = daily?.meters_per_point ?? 10;
  const score = saved.results.reduce((s, r) => s + r.points, 0);
  const depth = saved.results.reduce((d, r) => d + dropOf(r), 0);
  const zone = daily ? zoneAt(daily.zones, depth) : null;
  const saveKey = daily ? `rb:dive:${daily.day}` : null;

  const update = useCallback(
    (next: Saved | ((current: Saved) => Saved)) => {
      const value = typeof next === "function" ? next(savedRef.current) : next;
      savedRef.current = value;
      setSaved(value);
      if (saveKey) persist(saveKey, value);
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
        savedRef.current = s;
        setSaved(s);
        if (s.results.length >= d.prompts.length) setPhase("done");
        else if (s.startedAt) setPhase("play"); // refreshing doesn't reset the clock
        else if (s.results.length > 0) {
          // Left between prompts: pick up at the next one with a fresh clock.
          const resumed = { ...s, startedAt: Date.now() };
          savedRef.current = resumed;
          setSaved(resumed);
          persist(`rb:dive:${d.day}`, resumed);
          setPhase("play");
        } else setPhase("intro");
      })
      .catch(() => setPhase("error"));
  }, []);

  const submit = useCallback(
    async (text: string, force = false): Promise<CheckResult | null> => {
      if (!daily || !prompt || phase !== "play" || submission.current) return null;
      submission.current = true;
      // Preloaded games go straight to the verdict in this event, without a loading state.
      if (!prompt.play) setSubmitting(true);
      const sentAt = Date.now();
      let accepted = false;
      try {
        const response = prompt.play
          ? localAttempt(prompt.play, text, force)
          : force
            ? { accepted: true as const, result: await api.guess(playerId(), prompt.id, text) }
            : await api.attempt(playerId(), prompt.id, text);
        if (!response.accepted) {
          if (!prompt.play) {
            const receivedAt = Date.now();
            setNow(receivedAt);
            update((current) => ({ ...current, startedAt: current.startedAt === null ? null : current.startedAt + receivedAt - sentAt }));
          }
          return response.check;
        }
        accepted = true;
        const r = response.result;
        const result = { ...r, raw: text, synced: !prompt.play };
        const current = savedRef.current;
        const next = { ...current, results: [...current.results, result], startedAt: null };
        update(next);
        // Flash the verdict, then the next prompt (its clock starts now) or the results.
        setPhase("flash");
        setTimeout(() => {
          if (next.results.length >= daily.prompts.length) return setPhase("done");
          const t = Date.now();
          setNow(t);
          // A background confirmation may have updated results during the animation.
          update((current) => ({ ...current, startedAt: t }));
          submission.current = false;
          setPhase("play");
        }, flashMs(result));
        return null;
      } catch {
        setPhase("error");
        return null;
      } finally {
        if (!accepted) submission.current = false;
        setSubmitting(false);
      }
    },
    [daily, prompt, phase, update],
  );

  // Persist first, then record guesses independently of the animation. Unsent entries survive refresh.
  useEffect(() => {
    if (!daily) return;
    saved.results.forEach((result, index) => {
      const id = daily.prompts[index]?.id;
      if (!id || result.synced !== false || syncing.current.has(id) || failed.current.has(id)) return;
      syncing.current.add(id);
      api.guess(playerId(), id, result.raw ?? result.answer ?? "")
        .then((confirmed) => update((current) => ({
          ...current,
          results: current.results.map((entry, i) => i === index ? { ...confirmed, raw: entry.raw, synced: true } : entry),
        })))
        .catch(() => {
          failed.current.add(id);
          setSonarLost(true);
        })
        .finally(() => syncing.current.delete(id));
    });
  }, [daily, saved.results, attempt, update]);

  const limitMs = (daily?.time_limit ?? 20) * 1000;
  const remaining = saved.startedAt ? Math.max(0, limitMs - (now - saved.startedAt)) : limitMs;

  useEffect(() => {
    if (phase !== "play" || submitting) return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [phase, idx, submitting]);

  // Post the finish, then read the board (so it includes us). If posting fails, still show the board.
  useEffect(() => {
    if (phase !== "done" || !daily || saved.results.some((result) => result.synced === false)) return;
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
  }, [phase, daily, saved.nickname, saved.results, attempt]);

  const retrySonar = useCallback(() => {
    failed.current.clear();
    setSonarLost(false);
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    addEventListener("online", retrySonar);
    return () => removeEventListener("online", retrySonar);
  }, [retrySonar]);

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
