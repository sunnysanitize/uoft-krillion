"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { Prompt } from "../lib/api";
import { complete, norm, typoOf } from "../lib/match";
import { TimerDial } from "./TimerDial";
import { Label, PixelButton } from "./ui";

export function PlayScreen({
  prompt,
  index,
  total,
  remaining,
  limit,
  submitting,
  onSubmit,
}: {
  prompt: Prompt;
  index: number;
  total: number;
  remaining: number;
  limit: number;
  submitting: boolean;
  onSubmit: (answer: string) => void;
}) {
  const [answer, setAnswer] = useState("");
  const [hi, setHi] = useState(-1); // highlighted autocomplete row
  const [typo, setTypo] = useState<{ from: string; to: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  // A spelling the player already saw a fix for; diving it again sends it as typed.
  const dismissed = useRef<string | null>(null);
  const suggestions = prompt.suggestions ?? [];
  const options = useMemo(() => complete(answer, suggestions), [answer, suggestions]);
  const showOptions = options.length > 0 && !(options.length === 1 && norm(options[0]) === norm(answer));

  useEffect(() => {
    setAnswer("");
    setTypo(null);
    dismissed.current = null;
    input.current?.focus();
  }, [prompt.id]);

  // Out of air: send whatever is typed (possibly nothing) exactly once.
  const fired = useRef<string | null>(null);
  useEffect(() => {
    if (remaining <= 0 && fired.current !== prompt.id) {
      fired.current = prompt.id;
      onSubmit(answer);
    }
  }, [remaining, prompt.id, answer, onSubmit]);

  function dive(text: string) {
    if (!text.trim() || submitting) return;
    // First submit of a near-miss spelling: offer the fix instead of spending the prompt.
    const fix = typo || norm(text) === dismissed.current ? null : typoOf(text, suggestions);
    if (fix) {
      dismissed.current = norm(text);
      setTypo({ from: text, to: fix });
      setAnswer(fix);
      return;
    }
    onSubmit(text);
  }

  function pick(s: string) {
    setAnswer(s);
    setHi(-1);
    setTypo(null);
    input.current?.focus();
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (!showOptions || typo) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      // Cycle through the rows and back to the text field (-1).
      const step = e.key === "ArrowDown" ? 1 : -1;
      setHi((h) => {
        const next = h + step;
        return next >= options.length ? -1 : next < -1 ? options.length - 1 : next;
      });
    } else if (e.key === "Enter" && hi >= 0 && hi < options.length) {
      e.preventDefault();
      pick(options[hi]);
    } else if (e.key === "Escape") {
      setHi(-1);
    }
  }

  return (
    <>
      <div className="fixed inset-x-0 top-[22vh] z-20 flex justify-center px-4 md:pr-48 sm:top-[25vh]">
        <section key={prompt.id} className="w-full max-w-2xl animate-surface border-2 border-line bg-trench/95 p-5 shadow-block sm:p-8">
          <Label className="text-sonar">
            Prompt {index + 1} of {total}
          </Label>
          <h1 className="mt-3 text-balance font-pixel text-[clamp(1.75rem,5vw,3rem)] font-medium leading-[1.08]">{prompt.text}</h1>
          <p className="mt-4 text-sm text-mist">▼ {prompt.hint} ▼</p>
        </section>
      </div>

      <form
        className="fixed inset-x-0 bottom-0 z-30 border-t-2 border-line bg-abyss/90 px-3 pb-4 pt-3 sm:px-5 md:pr-48"
        onSubmit={(e) => {
          e.preventDefault();
          dive(answer);
        }}
      >
        <div className="relative mx-auto max-w-2xl">
          {typo && (
            <div className="absolute inset-x-0 bottom-full mb-3 flex justify-center" role="status">
              <div className="border-2 border-line bg-trench px-4 py-2.5 text-center shadow-block">
                <div className="text-sm">
                  <span className="text-mist">“{typo.from}”</span> <span className="text-slate">→</span>{" "}
                  <span className="text-sonar">“{typo.to}”</span>
                </div>
                <div className="mt-1 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.2em] text-slate">
                  <span>Dive again to confirm ·</span>
                  <button
                    type="button"
                    onClick={() => onSubmit(typo.from)}
                    className="cursor-pointer uppercase tracking-[0.2em] text-mist underline underline-offset-2 hover:text-ink"
                  >
                    keep mine
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 sm:gap-3">
            <TimerDial remaining={remaining} limit={limit} />
            <div className="relative min-w-0 flex-1">
              {showOptions && !typo && (
                <ul
                  id="answer-options"
                  role="listbox"
                  className="absolute inset-x-0 bottom-full mb-2 border-2 border-line bg-trench shadow-block"
                >
                  {options.map((o, i) => (
                    <li
                      key={o}
                      id={`answer-option-${i}`}
                      role="option"
                      aria-selected={i === hi}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        pick(o);
                      }}
                      className={`cursor-pointer px-4 py-2 text-sm ${i === hi ? "bg-uoft text-ink" : "text-mist hover:bg-deep hover:text-ink"}`}
                    >
                      {o}
                    </li>
                  ))}
                </ul>
              )}
              <label htmlFor="answer" className="sr-only">
                Your answer
              </label>
              <input
                id="answer"
                ref={input}
                role="combobox"
                aria-expanded={showOptions}
                aria-controls="answer-options"
                aria-autocomplete="list"
                aria-activedescendant={showOptions && hi >= 0 ? `answer-option-${hi}` : undefined}
                className="w-full border-2 border-sonar/70 bg-trench px-3 py-3.5 text-base text-ink placeholder:text-slate focus:border-sonar focus:outline-none sm:px-4 sm:text-lg"
                placeholder="type one answer…"
                maxLength={80}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                value={answer}
                onKeyDown={onKey}
                onChange={(e) => {
                  setAnswer(e.target.value);
                  setHi(-1);
                  setTypo(null);
                }}
                disabled={submitting}
              />
              {/* Air left, as a bar under the field */}
              <div className="mt-1.5 h-1 bg-deep">
                <div
                  className={`h-full transition-[width] duration-100 ease-linear ${remaining <= 5000 ? "bg-coral" : "bg-sonar"}`}
                  style={{ width: `${(remaining / limit) * 100}%` }}
                />
              </div>
            </div>
            <PixelButton disabled={submitting || !answer.trim()} className="self-start px-3.5! text-base! sm:px-7! sm:text-lg!">
              Dive
            </PixelButton>
          </div>
        </div>
      </form>
    </>
  );
}
