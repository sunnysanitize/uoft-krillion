"use client";

import { useRef, type FormEvent } from "react";
import type { Daily } from "../lib/api";
import { CREATURE, maxScore, meters, TONE_LABEL, TONE_TEXT, type Tone } from "../lib/game";
import { SCENE } from "./Scene";
import { Label, PixelButton } from "./ui";

/** Title shot: name in the sky, sign-in just under the waterline, then one button down. */
export function IntroScreen({
  daily,
  leaving,
  onBegin,
}: {
  daily: Daily;
  leaving: boolean;
  onBegin: () => void;
}) {
  const howTo = useRef<HTMLDialogElement>(null);
  const go = (e: FormEvent) => {
    e.preventDefault();
    onBegin();
  };

  return (
    <div
      className={`fixed inset-0 z-20 flex flex-col transition-[opacity,transform,filter] duration-[900ms] ease-[cubic-bezier(.6,0,.8,.4)] ${
        leaving ? "pointer-events-none -translate-y-[45vh] scale-110 opacity-0 blur-md" : ""
      }`}
    >
      <header
        className="flex flex-col items-center px-5 pt-[9vh] text-center"
        style={{ height: `${SCENE.SURFACE_VH}vh` }}
      >
        <Label className="text-lightblue! float-in float-in-1">Dive No.{String(daily.number).padStart(3, "0")} · today</Label>
        <h1
          className="mt-4 float-in float-in-2 text-uoft font-pixel text-[clamp(3.25rem,11vw,6.5rem)] font-bold leading-[0.85] tracking-tight"
          aria-label="UofT Krillion"
        >
          <WavyText text="UofT" className="text-lightblue" />
          <span className="inline-block w-[0.3em]" />
          <WavyText text="Krillion" offset={5} />
        </h1>
        <p className="mt-5 float-in float-in-3 font-pixel text-lg uppercase tracking-[0.24em] text-uoft sm:text-xl">Deeper dive into UofT</p>
        <p className="mt-3 float-in float-in-4 text-sm text-uoft/90">
          {daily.prompts.length} prompts · {daily.time_limit} seconds each · rarer answers sink deeper
        </p>
      </header>

      <form onSubmit={go} className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-4 px-5 pb-6">
        <fieldset disabled={leaving} className="contents">
        <div className="float-in float-in-5">
          <PixelButton type="submit" autoFocus className="w-full animate-breathe py-4! text-xl! tracking-[0.3em]!">
            ▼ Begin descent ▼
          </PixelButton>
        </div>


        <div className="float-in float-in-7 flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={() => howTo.current?.showModal()}
            className="cursor-pointer uppercase tracking-[0.25em] text-foam underline underline-offset-4 hover:text-ink"
          >
            How it works
          </button>
          <span className="text-ink/70">Fan-made. Not affiliated with UofT.</span>
        </div>
        </fieldset>
      </form>

      <dialog
        ref={howTo}
        className="m-auto w-[min(32rem,calc(100vw-2rem))] border-2 border-line bg-trench p-6 text-ink shadow-block backdrop:bg-abyss/70"
        onClick={(e) => e.target === howTo.current && howTo.current?.close()}
      >
        <Label>How it works</Label>
        <ol className="mt-4 space-y-3 text-sm leading-relaxed text-mist">
          <li>
            <b className="font-medium text-ink">Answer each prompt</b> before your {daily.time_limit} seconds of air run out.
          </li>
          <li>
            <b className="font-medium text-ink">The fewer divers who said it, the deeper you sink.</b> Obvious answers barely get you wet.
          </li>
          <li>
            Every prompt hides one <b className="font-medium text-gold">One in a Krillion</b> answer. A perfect day scores{" "}
            {maxScore(daily.prompts.length).toLocaleString("en-CA")}.
          </li>
        </ol>
        <Label className="mt-6">What you can catch</Label>
        <ol className="mt-3 space-y-1.5">
          {TIERS.map(([tone, points]) => (
            <li key={tone} className="grid grid-cols-[3.5rem_1fr_auto] items-center gap-3 text-sm">
              <img src={CREATURE[tone]!.src} alt="" className="h-7 w-auto justify-self-center" />
              <span>
                <span className={TONE_TEXT[tone]}>{TONE_LABEL[tone]}</span>
                <span className="ml-2 text-xs text-slate">{CREATURE[tone]!.name}</span>
              </span>
              <span className="font-pixel tabular-nums text-mist">{points}</span>
            </li>
          ))}
        </ol>
        <Label className="mt-6">The descent</Label>
        <ol className="mt-3 border-l-2 border-line">
          {daily.zones.map((z) => (
            <li key={z.name} className="flex justify-between gap-4 py-1 pl-3 text-sm">
              <span>{z.name}</span>
              <span className="tabular-nums text-slate">{meters(z.start)}</span>
            </li>
          ))}
        </ol>
        <form method="dialog" className="mt-6">
          <PixelButton className="w-full">Got it</PixelButton>
        </form>
      </dialog>
    </div>
  );
}

// Mirrors the server's TIER_POINTS / GOLDEN_POINTS.
const TIERS: [Tone, number][] = [["common", 10], ["uncommon", 30], ["rare", 60], ["deepcut", 85], ["golden", 100]];

/** Each letter bobs on its own beat, so the title looks like it's floating on the swell. */
function WavyText({ text, className = "", offset = 0 }: { text: string; className?: string; offset?: number }) {
  return (
    <span className={className} aria-hidden>
      {[...text].map((ch, i) => (
        <span key={i} className="inline-block animate-letter" style={{ animationDelay: `${-(i + offset) * 0.18}s` }}>
          {ch}
        </span>
      ))}
    </span>
  );
}
