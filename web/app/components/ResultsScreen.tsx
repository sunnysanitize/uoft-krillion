"use client";

import { useEffect, useState } from "react";
import { api, type AnswerRow, type Daily, type FinishResult, type GuessResult } from "../lib/api";
import { playerId, toneOfRarity } from "../lib/game";
import { clock, CREATURE, dropOf, maxScore, meters, msToNextDive, shareGlyph, TONE_BG, TONE_LABEL, TONE_TEXT, toneOf, zoneAt, ZONE_LINE } from "../lib/game";
import { DiveLog } from "./DiveLog";
import { Label, PixelButton } from "./ui";

export function ResultsScreen({
  daily,
  results,
  score,
  depth,
  mpp,
  finish,
  sonarLost,
  onRetry,
}: {
  daily: Daily;
  results: GuessResult[];
  score: number;
  depth: number;
  mpp: number;
  finish: FinishResult | null;
  sonarLost: boolean;
  onRetry: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [canShare, setCanShare] = useState(false);
  const [left, setLeft] = useState<number | null>(null);
  const zone = zoneAt(daily.zones, depth);

  useEffect(() => {
    setCanShare(typeof navigator.share === "function");
    const tick = () => setLeft(msToNextDive());
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  const text = `UofT Krillion No.${daily.number} · ${meters(depth)} · ${zone.name}\n${results.map(shareGlyph).join("")}\nDeeper dive into UofT`;
  const copy = () =>
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });

  return (
    // Fades in once the camera has sunk to the real depth (the Scene transition is 1.8s).
    <div className="fixed inset-0 z-20 overflow-y-auto bg-abyss/80 backdrop-blur-[2px] animate-fadein [animation-delay:1.6s]">
      <div className="mx-auto w-full max-w-3xl px-5 pb-16 pt-8 sm:pt-12">
        <header className="flex items-baseline justify-between gap-4">
          <div className="font-pixel text-2xl font-bold">
            <span className="text-sonar">UofT</span> Krillion
          </div>
          <Label>Dive No.{String(daily.number).padStart(3, "0")} complete</Label>
        </header>

        {/* Headline: score, depth, zone */}
        <section className="mt-10 animate-surface">
          <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
            <span className="font-pixel text-[clamp(4rem,16vw,7rem)] font-bold leading-[0.85] tabular-nums">{score}</span>
            <span className="pb-2 font-pixel text-xl text-slate">/{maxScore(daily.prompts.length).toLocaleString("en-CA")}</span>
            <span className="pb-2 font-pixel text-xl text-sonar">-{meters(depth)}</span>
          </div>
          <p className="mt-3 text-lg text-ink">{zone.name}</p>
        </section>

        {/* Where you landed among today's divers */}
        <section className="mt-8">
          <div className="relative h-2 bg-deep">
            <div className="segments h-full bg-sonar" style={{ width: `${finish?.percentile ?? 0}%` }} />
            {finish && (
              <div className="absolute -top-2 h-6 w-0.5 bg-gold" style={{ left: `${finish.percentile}%` }}>
                <span className="absolute left-1/2 top-7 -translate-x-1/2 font-pixel text-xs text-gold">YOU</span>
              </div>
            )}
          </div>
          <p className="mt-9 text-sm uppercase tracking-[0.2em] text-sonar">
            {!finish && sonarLost ? (
              <>
                Sonar lost.{" "}
                <button onClick={onRetry} className="cursor-pointer uppercase underline underline-offset-4 hover:text-foam">
                  Retry
                </button>
              </>
            ) : !finish
              ? "Pinging the sonar…"
              : finish.players > 1
                ? `Deeper than ${finish.percentile}% of ${finish.players.toLocaleString("en-CA")} divers today`
                : "First diver of the day. The bar is yours."}
          </p>
        </section>

        <section className="mt-12">
          <div className="flex items-center gap-3">
            <Label>Dive log</Label>
            <Label className="text-slate">deeper = rarer</Label>
            <span className="h-px flex-1 border-t border-dashed border-line" />
          </div>
          <div className="mt-4">
            <DiveLog results={results} prompts={daily.prompts.map((p) => p.text)} />
          </div>
          <ol className="mt-6 space-y-3">
            {results.map((r, i) => (
              <AnswerCard key={i} n={i + 1} promptId={daily.prompts[i]?.id ?? ""} prompt={daily.prompts[i]?.text ?? ""} result={r} delay={1.9 + i * 0.12} />
            ))}
          </ol>
        </section>

        <div className="mt-10 grid grid-cols-[1fr_auto] gap-3">
          <PixelButton onClick={copy} className="py-4!">
            {copied ? "Copied" : "Copy result"}
          </PixelButton>
          {canShare && (
            <PixelButton variant="ghost" onClick={() => navigator.share({ text }).catch(() => {})}>
              Share…
            </PixelButton>
          )}
        </div>

        <section className="mt-12">
          <div className="flex items-center gap-3">
            <Label>The descent</Label>
            <span className="h-px flex-1 border-t border-dashed border-line" />
          </div>
          <ol className="mt-3">
            {daily.zones.map((z, i) => {
              const next = daily.zones[i + 1];
              const here = z.name === zone.name;
              return (
                <li
                  key={z.name}
                  className={`grid grid-cols-[7.5rem_1fr] gap-4 border-b border-line/60 py-3 text-sm last:border-0 sm:grid-cols-[9rem_12rem_1fr] ${
                    here ? "text-ink" : "text-slate"
                  }`}
                >
                  <span className={`font-pixel tabular-nums ${here ? "text-sonar" : ""}`}>
                    {z.start.toLocaleString("en-CA")}
                    {next ? `–${(next.start - 1).toLocaleString("en-CA")}` : "+"} m
                  </span>
                  <span className={here ? "text-ink" : "text-mist"}>{z.name}</span>
                  <span className="col-span-2 text-xs text-slate sm:col-span-1 sm:text-sm">{ZONE_LINE[z.name] ?? ""}</span>
                </li>
              );
            })}
          </ol>
        </section>

        <p className="mt-8 text-center text-xs text-slate">
          Next dive in <span className="font-pixel tabular-nums text-mist">{left === null ? "--:--:--" : clock(left)}</span>. Go to
          class.
        </p>
      </div>
    </div>
  );
}

/** One prompt's verdict, shown only once the dive is over. */
function AnswerCard({
  n,
  promptId,
  prompt,
  result: r,
  delay,
}: {
  n: number;
  promptId: string;
  prompt: string;
  result: GuessResult;
  delay: number;
}) {
  const tone = toneOf(r);
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<AnswerRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  // Fetch the full list the first time it's opened.
  function toggle() {
    setOpen((o) => !o);
    if (rows || !promptId) return;
    setFailed(false);
    api
      .answers(playerId(), promptId)
      .then(setRows)
      .catch(() => setFailed(true));
  }
  const typed = r.raw?.trim();
  const top = r.top.slice(0, 3);
  return (
    <li className="animate-surface border-2 border-line bg-trench/80 p-4" style={{ animationDelay: `${delay}s` }}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 text-xs text-slate">
          <span className="tabular-nums">{n}.</span> {prompt}
        </span>
        <span className="shrink-0 font-pixel tabular-nums text-mist">+{r.points} · {meters(dropOf(r))}</span>
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {CREATURE[tone] ? (
          <img src={CREATURE[tone]!.src} alt={CREATURE[tone]!.name} title={CREATURE[tone]!.name} className="h-6 w-auto shrink-0 self-center" />
        ) : (
          <span className={`size-2.5 shrink-0 self-center ${TONE_BG[tone]}`} />
        )}
        <span className="font-pixel text-xl text-ink">{r.valid ? r.answer : typed ? `“${typed}”` : "No answer"}</span>
        <span className={`text-sm uppercase tracking-[0.2em] ${TONE_TEXT[tone]}`}>{TONE_LABEL[tone]}</span>
        {r.valid && <span className="text-xs text-mist">{r.share_pct}% said it</span>}
      </div>
      <div className="mt-2 space-y-1 text-xs">
        {!r.golden && (
          <p className="text-mist">
            One in a Krillion: <b className="font-medium text-gold">{r.golden_answer}</b>
          </p>
        )}
        {top.length > 0 && (
          <p className="text-slate">
            Most said:{" "}
            {top.map((t, j) => (
              <span key={t.answer} className={t.answer === r.answer ? "text-sonar" : "text-mist"}>
                {j > 0 && " · "}
                {t.answer} {t.pct}%
              </span>
            ))}
          </p>
        )}
      </div>

      <button
        onClick={toggle}
        aria-expanded={open}
        className="mt-3 cursor-pointer text-[11px] uppercase tracking-[0.25em] text-sonar hover:text-foam"
      >
        {open ? "Hide answers ▴" : "Show all answers ▾"}
      </button>
      {open && (
        <div className="mt-2 max-h-80 overflow-y-auto border-t border-line/60 pt-2">
          {failed ? (
            <p className="text-xs text-slate">Couldn’t load the answers. Try again in a moment.</p>
          ) : !rows ? (
            <p className="text-xs text-slate">Loading…</p>
          ) : (
            <ol className="space-y-0.5">
              {rows.map((a) => {
                const t = toneOfRarity(a.rarity);
                return (
                  <li
                    key={a.answer}
                    className={`grid grid-cols-[0.75rem_1fr_auto_auto] items-center gap-3 px-1 py-0.5 text-sm ${a.yours ? "bg-uoft/60" : ""}`}
                  >
                    <span className={`size-2 ${TONE_BG[t]}`} title={TONE_LABEL[t]} />
                    <span className={`min-w-0 truncate ${a.golden ? "text-gold" : "text-ink"}`}>
                      {a.answer}
                      {a.yours && <span className="ml-2 text-[10px] uppercase tracking-[0.2em] text-sonar">you</span>}
                    </span>
                    <span className="text-xs tabular-nums text-slate">{a.pct}%</span>
                    <span className={`w-10 text-right font-pixel tabular-nums ${TONE_TEXT[t]}`}>+{a.points}</span>
                    {a.golden && r.golden_why && (
                      <span className="col-span-3 col-start-2 text-xs text-mist">{r.golden_why}</span>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}
