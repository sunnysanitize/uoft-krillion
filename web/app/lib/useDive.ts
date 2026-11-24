"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Daily, FinishResult, GuessResult, Leaderboard } from "./api";
import { persist, playerId, storage, zoneAt } from "./game";

export type Phase = "loading" | "intro" | "play" | "reveal" | "done" | "error";

type Saved = {
  results: GuessResult[];
  startedAt: number | null;
  nickname: string;
  college: string | null;
};

/** All game state and server calls for one day's dive. Screens stay presentational. */
export function useDive() {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [saved, setSaved] = useState<Saved>({ results: [], startedAt: null, nickname: "", college: null });
  const [now, setNow] = useState(() => Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [finish, setFinish] = useState<FinishResult | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);

  const idx = saved.results.length;
  const prompt = daily?.prompts[idx];
  const mpp = daily?.meters_per_point ?? 10;
  const score = saved.results.reduce((s, r) => s + r.points, 0);
  const depth = score * mpp;
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
          nickname: storage("rb:nickname", ""),
          college: storage<string | null>("rb:college", null),
        });
        setSaved(s);
        if (s.results.length >= d.prompts.length) setPhase("done");
        else if (s.startedAt) setPhase("play"); // refreshing doesn't reset the clock
        else if (s.results.length > 0) setPhase("reveal");
        else setPhase("intro");
      })
      .catch(() => setPhase("error"));
  }, []);

  const submit = useCallback(
    async (text: string) => {
      if (!daily || !prompt || submitting) return;
      setSubmitting(true);
      try {
        const r = await api.guess(playerId(), prompt.id, text);
        update({ ...saved, results: [...saved.results, { ...r, raw: text }], startedAt: null });
        setPhase("reveal");
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
      .finish(playerId(), name, saved.college)
      .then(setFinish)
      .catch(() => setSonarLost(true))
      .finally(() =>
        api
          .leaderboard()
          .then(setBoard)
          .catch(() => setSonarLost(true)),
      );
  }, [phase, daily, saved.nickname, saved.college, attempt]);

  const retrySonar = () => setAttempt((n) => n + 1);

  function next() {
    if (!daily) return;
    if (idx >= daily.prompts.length) return setPhase("done");
    const t = Date.now();
    setNow(t);
    update({ ...saved, startedAt: t });
    setPhase("play");
  }

  function begin() {
    persist("rb:nickname", saved.nickname);
    persist("rb:college", saved.college);
    next();
  }

  const setProfile = (p: Partial<Pick<Saved, "nickname" | "college">>) => setSaved({ ...saved, ...p });

  return {
    daily,
    phase,
    results: saved.results,
    nickname: saved.nickname,
    college: saved.college,
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
    next,
    begin,
    setProfile,
  };
}

export type Dive = ReturnType<typeof useDive>;
