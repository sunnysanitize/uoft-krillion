"use client";

import { useEffect, useRef, useState } from "react";
import { type CheckResult, type Prompt } from "../lib/api";
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
  onSubmit: (answer: string, force?: boolean) => Promise<CheckResult | null>;
}) {
  const [answer, setAnswer] = useState("");
  // After Enter: a "did you mean" to accept with Enter again, or a rejection to retype.
  const [suggestion, setSuggestion] = useState<string | null>(null);
  // A miss to show and shake: unrecognized, or recognized but wrong. `n` re-triggers the shake.
  const [rejected, setRejected] = useState<{ text: string; wrong: boolean; n: number } | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAnswer("");
    setSuggestion(null);
    setRejected(null);
    input.current?.focus();
  }, [prompt.id]);

  useEffect(() => {
    if (!submitting) input.current?.focus();
  }, [submitting]);

  // Out of air: send whatever is typed (possibly nothing) exactly once.
  const fired = useRef<string | null>(null);
  useEffect(() => {
    if (!submitting && remaining <= 0 && fired.current !== prompt.id) {
      fired.current = prompt.id;
      onSubmit(answer, true);
    }
  }, [remaining, prompt.id, answer, onSubmit, submitting]);

  // Only right answers spend the prompt. Wrong ones get another go until the clock runs out.
  async function dive(typed: string) {
    if (!typed.trim() || submitting) return;
    // Taking a "did you mean" still goes through the check, so it can't sneak a wrong answer in.
    const text = suggestion ?? typed;
    if (suggestion) {
      setAnswer(suggestion);
      setSuggestion(null);
    }
    const r = await onSubmit(text);
    if (!r) return;
    if (!r.recognized && r.suggestion) setSuggestion(r.suggestion);
    else setRejected((prev) => ({ text, wrong: r.recognized, n: (prev?.n ?? 0) + 1 }));
  }

  return (
    <>
      <div className="fixed inset-x-0 top-[22vh] z-20 flex animate-drift-y justify-center px-4 sm:top-[25vh]">
        <div className="tilt w-full max-w-2xl">
        <section key={prompt.id} className="w-full animate-slam border-2 border-line bg-trench/95 p-5 shadow-block sm:p-8">
          <Label className="text-sonar">
            Prompt {index + 1} of {total}
          </Label>
          <h1 className="mt-3 text-balance font-pixel text-[clamp(1.75rem,5vw,3rem)] font-medium leading-[1.18]">{prompt.text}</h1>
          <p className="mt-4 text-sm text-mist">▼ {prompt.hint} ▼</p>
        </section>
        </div>
      </div>

      <form
        className="fixed inset-x-0 bottom-0 z-30 px-3 pb-5 pt-3 sm:px-5"
        aria-busy={submitting}
        onSubmit={(e) => {
          e.preventDefault();
          dive(answer);
        }}
      >
        <div className="relative mx-auto max-w-2xl">
          {(suggestion || rejected) && (
            <div className="absolute inset-x-0 bottom-full mb-3 flex justify-center" role="status">
              {suggestion ? (
                <div className="animate-surface border-2 border-sonar bg-trench px-4 py-2.5 text-center shadow-block">
                  <div className="text-sm">
                    <span className="text-mist">Did you mean</span> <span className="text-sonar">“{suggestion}”</span>
                    <span className="text-mist">?</span>
                  </div>
                  <div className="mt-1 text-[11px] uppercase tracking-[0.2em] text-slate">Enter to dive with it · keep typing to change</div>
                </div>
              ) : (
                <div key={rejected!.n} className="animate-shake border-2 border-coral bg-trench/95 px-4 py-2.5 text-center text-sm shadow-block">
                  <span className="text-coral">“{rejected!.text}”</span>{" "}
                  <span className="text-mist">{rejected!.wrong ? "isn’t it. Keep trying!" : "isn’t recognized. Try another."}</span>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 sm:gap-3">
            <TimerDial remaining={remaining} limit={limit} />
            <div className="relative min-w-0 flex-1">
              <label htmlFor="answer" className="sr-only">
                Your answer
              </label>
              <input
                id="answer"
                ref={input}
                className="w-full border-2 border-sonar/70 bg-trench/70 px-3 py-3.5 backdrop-blur-sm text-base text-ink placeholder:text-slate focus:border-sonar focus:outline-none sm:px-4 sm:text-lg"
                placeholder="type one answer…"
                maxLength={80}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                value={answer}
                onChange={(e) => {
                  setAnswer(e.target.value);
                  setSuggestion(null);
                  setRejected(null);
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
            <PixelButton disabled={submitting || !answer.trim()} className="self-start min-w-24 px-3.5! text-base! sm:px-7! sm:text-lg!">
              Dive
            </PixelButton>
          </div>
        </div>
      </form>
    </>
  );
}
