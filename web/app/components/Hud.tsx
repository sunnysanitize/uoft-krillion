"use client";

import { useEffect, useRef, useState } from "react";
import { meters } from "../lib/game";
import { Label } from "./ui";

/** The depth readout counts up to its new value over `ms` (the camera's sink), instead of jumping. */
function useTicking(target: number, ms: number) {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now();
    const begin = from.current;
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(begin + (target - begin) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else from.current = target;
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
      from.current = target;
    };
  }, [target, ms]);
  return shown;
}

/** Top bar during the dive: how deep your points have taken you, and progress through the prompts. */
export function Hud({
  answered,
  total,
  current,
  depth,
  zone,
  sink,
}: {
  answered: number;
  total: number;
  current: number;
  depth: number;
  zone: string;
  sink: number;
}) {
  const shown = useTicking(depth, sink);
  return (
    <header className="fixed inset-x-0 top-0 z-30 flex items-start justify-center gap-3 px-3 pt-3 sm:px-8 sm:pt-5">
      <div className="min-w-32 animate-drift-y border-2 border-line bg-trench/90 px-4 py-2 shadow-block [animation-delay:-1s]">
        <Label>Depth</Label>
        <div className="font-pixel text-2xl leading-tight tabular-nums text-sonar">{meters(shown)}</div>
        <div className="truncate text-[11px] text-mist max-sm:hidden">{zone}</div>
      </div>
      <div className="flex animate-drift-y flex-col items-center gap-2 border-2 border-line bg-trench/90 px-4 py-2.5 shadow-block [animation-delay:-2s]">
        <PromptTrack answered={answered} total={total} current={current} />
        <Label className="tracking-[0.24em]">
          Prompt {Math.min(current + 1, total)} of {total}
        </Label>
      </div>
    </header>
  );
}

/** Answered prompts fill in; the live one blinks. */
export function PromptTrack({ answered, total, current }: { answered: number; total: number; current: number }) {
  return (
    <ol className="flex gap-1 sm:gap-1.5" aria-label={`Prompt ${current + 1} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <li
          key={i}
          className={`size-3 border-2 sm:size-3.5 ${
            i < answered ? "border-transparent bg-mist" : i === current ? "border-ink animate-blink" : "border-mist/40 bg-abyss/60"
          }`}
        />
      ))}
    </ol>
  );
}
