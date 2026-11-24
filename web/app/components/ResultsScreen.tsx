"use client";

import { useEffect, useState } from "react";
import type { Daily, FinishResult, GuessResult, Leaderboard } from "../lib/api";
import { clock, maxScore, meters, msToNextDive, shareGlyph, TONE_BG, toneOf, zoneAt, ZONE_LINE } from "../lib/game";
import { DiveLog } from "./DiveLog";
import { Standings } from "./Standings";
import { Label, PixelButton } from "./ui";

export function ResultsScreen({
  daily,
  results,
  score,
  depth,
  mpp,
  finish,
  board,
  nickname,
  sonarLost,
  onRetry,
}: {
  daily: Daily;
  results: GuessResult[];
  score: number;
  depth: number;
  mpp: number;
  finish: FinishResult | null;
  board: Leaderboard | null;
  nickname: string;
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

  const text = `KrillionTO No.${daily.number} · ${meters(depth)} · ${zone.name}\n${results.map(shareGlyph).join("")}\nDeeper dive into UofT`;
  const copy = () =>
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });

  return (
    <div className="fixed inset-0 z-20 overflow-y-auto bg-abyss/80 backdrop-blur-[2px]">
      <div className="mx-auto w-full max-w-3xl px-5 pb-16 pt-8 sm:pt-12">
        <header className="flex items-baseline justify-between gap-4">
          <div className="font-pixel text-2xl font-bold">
            Krillion<span className="text-sonar">TO</span>
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
            <DiveLog results={results} mpp={mpp} prompts={daily.prompts.map((p) => p.text)} />
          </div>
          <ol className="mt-4 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {results.map((r, i) => (
              <li key={i} className="flex min-w-0 items-center gap-2">
                <span className="w-4 shrink-0 text-xs tabular-nums text-slate">{i + 1}</span>
                <span className={`size-2.5 shrink-0 ${TONE_BG[toneOf(r)]}`} />
                <span className="truncate text-ink">{r.answer ?? <span className="text-coral">no answer</span>}</span>
                <span className="ml-auto shrink-0 tabular-nums text-mist">{meters(r.points * mpp)}</span>
              </li>
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

        <div className="mt-12">
          <Standings board={board} lost={sonarLost} mpp={mpp} you={nickname.trim() || "anon goose"} />
        </div>

        <p className="mt-8 text-center text-xs text-slate">
          Next dive in <span className="font-pixel tabular-nums text-mist">{left === null ? "--:--:--" : clock(left)}</span>. Go to
          class.
        </p>
      </div>
    </div>
  );
}
