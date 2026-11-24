"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, Daily, FinishResult, GuessResult, Leaderboard } from "./lib/api";

type Phase = "loading" | "intro" | "play" | "reveal" | "done" | "error";

type Saved = {
  results: GuessResult[];
  startedAt: number | null;
  nickname: string;
  college: string | null;
};

// Depth at which the ocean is fully dark and the gauge bottoms out.
const MAX_DEPTH = 7000;

const EMOJI: Record<string, string> = {
  Legendary: "🟪",
  Rare: "🟦",
  Uncommon: "🟩",
  Common: "🟨",
  Basic: "⬜",
};

const BUBBLES = Array.from({ length: 14 }, (_, i) => ({
  left: (i * 37) % 100,
  size: 4 + ((i * 7) % 10),
  delay: (i * 1.3) % 9,
  duration: 7 + ((i * 5) % 8),
}));

function storage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

function playerId(): string {
  let id = storage<string | null>("rb:player", null);
  if (!id) {
    id = crypto.randomUUID();
    persist("rb:player", id);
  }
  return id;
}

function emoji(r: GuessResult) {
  if (r.golden) return "🦐";
  return r.rarity ? EMOJI[r.rarity] : "⬛";
}

const meters = (n: number) => `${n.toLocaleString()} m`;

export default function Game() {
  const [daily, setDaily] = useState<Daily | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [saved, setSaved] = useState<Saved>({ results: [], startedAt: null, nickname: "", college: null });
  const [answer, setAnswer] = useState("");
  const [now, setNow] = useState(Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [finish, setFinish] = useState<FinishResult | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const idx = saved.results.length;
  const prompt = daily?.prompts[idx];
  const mpp = daily?.meters_per_point ?? 10;
  const depth = saved.results.reduce((s, r) => s + r.points, 0) * mpp;
  const zone = daily ? [...daily.zones].reverse().find((z) => depth >= z.start)?.name ?? "" : "";
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
        setAnswer("");
        setPhase("reveal");
      } catch {
        setPhase("error");
      } finally {
        setSubmitting(false);
      }
    },
    [daily, prompt, saved, submitting, update],
  );

  const remaining =
    daily && saved.startedAt ? Math.max(0, daily.time_limit * 1000 - (now - saved.startedAt)) : 0;

  useEffect(() => {
    if (phase !== "play") return;
    inputRef.current?.focus();
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [phase, idx]);

  useEffect(() => {
    if (phase === "play" && saved.startedAt && remaining <= 0) submit(answer);
  }, [phase, remaining, saved.startedAt, submit, answer]);

  useEffect(() => {
    if (phase !== "done" || !daily) return;
    const name = saved.nickname.trim() || "anon goose";
    api
      .finish(playerId(), name, saved.college)
      .then(setFinish)
      .then(() => api.leaderboard())
      .then(setBoard)
      .catch(() => {});
  }, [phase, daily, saved.nickname, saved.college]);

  function start(e?: FormEvent) {
    e?.preventDefault();
    persist("rb:nickname", saved.nickname);
    persist("rb:college", saved.college);
    next();
  }

  function next() {
    if (!daily) return;
    if (idx >= daily.prompts.length) return setPhase("done");
    const t = Date.now();
    setNow(t);
    update({ ...saved, startedAt: t });
    setPhase("play");
  }

  function share() {
    if (!daily) return;
    const grid = saved.results.map(emoji).join("");
    const text = `Rarest Blue #${daily.number} · ${meters(depth)} · ${zone}\n${grid}\nHow deep can you dive?`;
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  if (phase === "loading")
    return (
      <Shell depth={0}>
        <p className="center glass-text">descending…</p>
      </Shell>
    );
  if (phase === "error" || !daily)
    return (
      <Shell depth={0}>
        <div className="card center">
          <h2>Lost signal</h2>
          <p className="muted">Is the Python backend running on :8000? Then refresh.</p>
        </div>
      </Shell>
    );

  const last = saved.results[saved.results.length - 1];

  return (
    <Shell depth={depth} number={daily.number} zones={daily.zones} showGauge={phase !== "intro"}>
      {phase === "intro" && (
        <form className="card intro" onSubmit={start}>
          <img className="hero-logo" src="/krill.png" alt="Pixel krill in Varsity Blue" width={132} height={132} />
          <h1 className="hero">
            Dive for the answer <em>nobody</em> else finds.
          </h1>
          <ol className="rules">
            <li>
              <b>{daily.prompts.length} UofT prompts</b>, {daily.time_limit} seconds each.
            </li>
            <li>
              Rarer answers sink you <b>deeper</b>. Obvious ones barely get you wet.
            </li>
            <li>
              Each prompt hides one <b className="gold">Golden Krill</b> answer worth a huge bonus.
            </li>
          </ol>
          <div className="row">
            <input
              className="field"
              placeholder="Nickname"
              maxLength={20}
              value={saved.nickname}
              onChange={(e) => setSaved({ ...saved, nickname: e.target.value })}
            />
            <select
              className="field"
              value={saved.college ?? ""}
              onChange={(e) => setSaved({ ...saved, college: e.target.value || null })}
            >
              <option value="">Represent a college…</option>
              {daily.colleges.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <button className="btn" type="submit">
            Start the dive
          </button>
        </form>
      )}

      {phase === "play" && prompt && (
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            if (answer.trim()) submit(answer);
          }}
        >
          <div className="step">
            Prompt {idx + 1} of {daily.prompts.length}
            <span className="clock">{Math.ceil(remaining / 1000)}s</span>
          </div>
          <div className="timer" aria-label={`${Math.ceil(remaining / 1000)} seconds left`}>
            <div
              className={`timer-fill ${remaining < 5000 ? "urgent" : ""}`}
              style={{ width: `${(remaining / (daily.time_limit * 1000)) * 100}%` }}
            />
          </div>
          <h2 className="prompt">{prompt.text}</h2>
          <p className="muted">{prompt.hint}</p>
          <div className="row">
            <input
              ref={inputRef}
              className="field big"
              placeholder="Your rarest answer"
              maxLength={80}
              autoComplete="off"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              disabled={submitting}
            />
            <button className="btn" disabled={submitting || !answer.trim()}>
              Dive
            </button>
          </div>
        </form>
      )}

      {phase === "reveal" && last && (
        <div className="card">
          <div className="step">
            Prompt {idx} of {daily.prompts.length} · {daily.prompts[idx - 1]?.text}
          </div>
          {last.golden ? (
            <div className="verdict golden">
              <img src="/krill.png" alt="" width={56} height={56} className="verdict-krill" />
              <div>
                <div className="verdict-answer">{last.answer}</div>
                <div className="small">You found the Golden Krill!</div>
              </div>
              <div className="points">+{meters(last.points * mpp)}</div>
            </div>
          ) : last.valid ? (
            <div className={`verdict rarity-${last.rarity?.toLowerCase()}`}>
              <div>
                <div className="verdict-answer">{last.answer}</div>
                <div className="small">
                  {last.rarity} · {last.share_pct}% said this
                </div>
              </div>
              <div className="points">+{meters(last.points * mpp)}</div>
            </div>
          ) : (
            <div className="verdict rarity-miss">
              <div>
                <div className="verdict-answer">{last.raw?.trim() ? `"${last.raw}"` : "Out of air"}</div>
                <div className="small">{last.raw?.trim() ? "Not on the list" : "The clock beat you"}</div>
              </div>
              <div className="points">+0 m</div>
            </div>
          )}
          {!last.golden && (
            <p className="golden-reveal">
              🦐 The Golden Krill was hiding at <b>{last.golden_answer}</b>
            </p>
          )}
          <h3>What everyone else said</h3>
          <ul className="bars">
            {last.top.map((t) => (
              <li key={t.answer} className={t.answer === last.answer ? "mine" : ""}>
                <span className="bar" style={{ width: `${Math.max(t.pct, 2)}%` }} />
                <span className="bar-label">{t.answer}</span>
                <span className="bar-pct">{t.pct}%</span>
              </li>
            ))}
          </ul>
          {last.deep_cuts.length > 0 && (
            <p className="muted small">Other deep cuts: {last.deep_cuts.join(" · ")}</p>
          )}
          <button className="btn" onClick={next} autoFocus>
            {idx >= daily.prompts.length ? "Surface for results" : "Keep diving ↓"}
          </button>
        </div>
      )}

      {phase === "done" && (
        <div className="card">
          <div className="final">
            <div className="muted small">You reached</div>
            <div className="final-depth">{meters(depth)}</div>
            <div className="final-zone">{zone}</div>
            {finish && finish.players > 1 && (
              <div className="muted small">
                Deeper than {finish.percentile}% of {finish.players} divers today
              </div>
            )}
          </div>
          <ul className="recap">
            {saved.results.map((r, i) => (
              <li key={i}>
                <span>{emoji(r)}</span>
                <span className="recap-q">{daily.prompts[i]?.text}</span>
                <span className="recap-a">{r.answer ?? "—"}</span>
                <span className="recap-p">{meters(r.points * mpp)}</span>
              </li>
            ))}
          </ul>
          <button className="btn" onClick={share}>
            {copied ? "Copied!" : "Share your dive"}
          </button>

          {board && (
            <div className="boards">
              <section>
                <h3>Deepest divers today</h3>
                <ol className="board">
                  {board.players.map((p, i) => (
                    <li key={i}>
                      <span>{p.nickname}</span>
                      <span className="muted small">{p.college ?? ""}</span>
                      <b>{meters(p.score * mpp)}</b>
                    </li>
                  ))}
                </ol>
              </section>
              <section>
                <h3>College standings</h3>
                {board.colleges.length === 0 ? (
                  <p className="muted small">No colleges repping yet. Be the first.</p>
                ) : (
                  <ol className="board">
                    {board.colleges.map((c) => (
                      <li key={c.college}>
                        <span>{c.college}</span>
                        <span className="muted small">{c.n} diving</span>
                        <b>{meters(c.avg * mpp)}</b>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>
          )}
          <p className="muted small center">New dive at midnight. Go to class.</p>
        </div>
      )}
    </Shell>
  );
}

function Shell({
  children,
  depth,
  number,
  zones = [],
  showGauge = false,
}: {
  children: React.ReactNode;
  depth: number;
  number?: number;
  zones?: { start: number; name: string }[];
  showGauge?: boolean;
}) {
  const f = Math.min(depth / MAX_DEPTH, 1);
  return (
    <>
      <div className="ocean" style={{ transform: `translateY(${-f * 85}%)` }} aria-hidden />
      <div className="bubbles" aria-hidden>
        {BUBBLES.map((b, i) => (
          <span
            key={i}
            style={{
              left: `${b.left}%`,
              width: b.size,
              height: b.size,
              animationDelay: `${b.delay}s`,
              animationDuration: `${b.duration}s`,
            }}
          />
        ))}
      </div>
      {showGauge && (
        <aside className="gauge" aria-label={`Depth ${meters(depth)}`}>
          {zones.map((z) => (
            <span key={z.name} className="tick" style={{ top: `${(z.start / MAX_DEPTH) * 100}%` }}>
              <span className="tick-label">{z.name}</span>
            </span>
          ))}
          <img className="gauge-krill" src="/krill.png" alt="" width={36} height={36} style={{ top: `${f * 100}%` }} />
        </aside>
      )}
      <main className="shell">
        <header className="top">
          <div className="brand">
            <img className="logo" src="/krill.png" alt="" width={36} height={36} />
            Rarest <span>Blue</span>
          </div>
          <div className="meta">
            {number !== undefined && <span>#{number}</span>}
            {showGauge && <span className="depth">{meters(depth)}</span>}
          </div>
        </header>
        {children}
        <footer className="foot">Fan-made for UofT students. Not affiliated with the University of Toronto.</footer>
      </main>
    </>
  );
}
