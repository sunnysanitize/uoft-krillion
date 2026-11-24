"use client";

import { useRef, type FormEvent } from "react";
import type { Daily } from "../lib/api";
import { maxScore, meters } from "../lib/game";
import { SCENE } from "./Scene";
import { Label, PixelButton } from "./ui";

/** Title shot: name in the sky, sign-in just under the waterline, then one button down. */
export function IntroScreen({
  daily,
  nickname,
  college,
  leaving,
  onProfile,
  onBegin,
}: {
  daily: Daily;
  nickname: string;
  college: string | null;
  leaving: boolean;
  onProfile: (p: { nickname?: string; college?: string | null }) => void;
  onBegin: () => void;
}) {
  const howTo = useRef<HTMLDialogElement>(null);
  const go = (e: FormEvent) => {
    e.preventDefault();
    onBegin();
  };

  return (
    <div
      className={`fixed inset-0 z-20 flex flex-col transition-[opacity,transform] duration-700 ease-out ${
        leaving ? "pointer-events-none -translate-y-24 opacity-0" : ""
      }`}
    >
      <header
        className="flex flex-col items-center px-5 pt-[9vh] text-center"
        style={{ height: `${SCENE.SURFACE_VH}vh` }}
      >
        <Label className="text-sonar">Dive No.{String(daily.number).padStart(3, "0")} · today</Label>
        <h1 className="mt-4 font-pixel text-[clamp(3.25rem,11vw,6.5rem)] font-bold leading-[0.85] tracking-tight">
          Krillion<span className="text-sonar">TO</span>
        </h1>
        <p className="mt-5 font-pixel text-lg uppercase tracking-[0.35em] text-foam sm:text-xl">Deeper dive into UofT</p>
        <p className="mt-3 text-sm text-mist">
          {daily.prompts.length} prompts · {daily.time_limit} seconds each · rarer answers sink deeper
        </p>
      </header>

      <form onSubmit={go} className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center gap-4 px-5 pb-6">
        <fieldset disabled={leaving} className="contents">
        <div className="grid grid-cols-1 gap-2 min-[480px]:grid-cols-2">
          <label className="sr-only" htmlFor="callsign">
            Callsign
          </label>
          <input
            id="callsign"
            className="border-2 border-line bg-abyss/80 px-4 py-3 text-base text-ink placeholder:text-slate focus:border-sonar focus:outline-none"
            placeholder="Callsign (anon goose)"
            maxLength={20}
            autoComplete="nickname"
            value={nickname}
            onChange={(e) => onProfile({ nickname: e.target.value })}
          />
          <label className="sr-only" htmlFor="college">
            College
          </label>
          <select
            id="college"
            className="appearance-none border-2 border-line bg-abyss/80 bg-[linear-gradient(45deg,transparent_50%,var(--color-mist)_50%),linear-gradient(135deg,var(--color-mist)_50%,transparent_50%)] bg-[length:6px_6px] bg-[position:calc(100%-22px)_center,calc(100%-16px)_center] bg-no-repeat px-4 py-3 text-base text-ink focus:border-sonar focus:outline-none"
            value={college ?? ""}
            onChange={(e) => onProfile({ college: e.target.value || null })}
          >
            <option value="">Represent a college</option>
            {daily.colleges.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>

        <PixelButton type="submit" className="w-full py-4! text-xl! tracking-[0.3em]!">
          ▼ Begin descent ▼
        </PixelButton>

        <div className="flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={() => howTo.current?.showModal()}
            className="cursor-pointer uppercase tracking-[0.25em] text-sonar underline underline-offset-4 hover:text-foam"
          >
            How it works
          </button>
          <span className="text-slate">Fan-made. Not affiliated with UofT.</span>
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
            Every prompt hides one <b className="font-medium text-gold">Golden Krill</b> answer worth +1,000 m. A perfect day
            scores {maxScore(daily.prompts.length).toLocaleString("en-CA")}.
          </li>
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
