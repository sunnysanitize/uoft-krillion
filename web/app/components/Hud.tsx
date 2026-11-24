import type { GuessResult } from "../lib/api";
import { meters, TONE_BG, toneOf } from "../lib/game";
import { Label } from "./ui";

/** Top bar during the dive: depth box, prompt track, score box. */
export function Hud({
  depth,
  zone,
  score,
  results,
  total,
  current,
}: {
  depth: number;
  zone: string;
  score: number;
  results: GuessResult[];
  total: number;
  current: number;
}) {
  return (
    <header className="fixed inset-x-0 top-0 z-30 grid grid-cols-[1fr_auto_1fr] items-start gap-3 px-3 pt-3 sm:px-8 sm:pt-5 md:pr-52">
      <Box className="justify-self-start">
        <Label>Depth</Label>
        <div className="font-pixel text-2xl leading-tight text-sonar tabular-nums sm:text-3xl">{meters(depth)}</div>
        <div className="truncate text-[11px] text-mist max-sm:hidden">{zone}</div>
      </Box>
      <div className="flex flex-col items-center gap-2 pt-2">
        <PromptTrack results={results} total={total} current={current} />
        <Label className="tracking-[0.24em] max-sm:hidden">
          Prompt {Math.min(current + 1, total)} of {total}
        </Label>
      </div>
      <Box className="justify-self-end text-right">
        <Label>Score</Label>
        <div className="font-pixel text-2xl leading-tight text-ink tabular-nums sm:text-3xl">{score.toLocaleString("en-CA")}</div>
      </Box>
    </header>
  );
}

function Box({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`min-w-0 border-2 border-line bg-trench/90 px-3 py-2 shadow-block sm:min-w-44 sm:px-4 sm:py-2.5 ${className}`}>
      {children}
    </div>
  );
}

/** Logged prompts take their rarity colour; the live one blinks. */
export function PromptTrack({ results, total, current }: { results: GuessResult[]; total: number; current: number }) {
  return (
    <ol className="flex gap-1 sm:gap-1.5" aria-label={`Prompt ${current + 1} of ${total}`}>
      {Array.from({ length: total }, (_, i) => {
        const r = results[i];
        return (
          <li
            key={i}
            className={`size-3 border-2 sm:size-3.5 ${
              r ? `${TONE_BG[toneOf(r)]} border-transparent` : i === current ? "border-ink animate-blink" : "border-mist/40 bg-abyss/60"
            }`}
          />
        );
      })}
    </ol>
  );
}
