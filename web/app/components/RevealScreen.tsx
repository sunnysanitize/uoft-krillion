import type { GuessResult } from "../lib/api";
import { meters, TONE_LABEL, TONE_LINE, TONE_TEXT, toneOf } from "../lib/game";
import { PixelButton } from "./ui";

/** Full-screen verdict after each answer, then one button to keep going. */
export function RevealScreen({
  result,
  last,
  mpp,
  onNext,
}: {
  result: GuessResult;
  last: boolean;
  mpp: number;
  onNext: () => void;
}) {
  const tone = toneOf(result);
  const typed = result.raw?.trim();
  const said = result.valid ? result.answer : typed;
  const line = tone === "miss" && !typed ? "The clock beat you to it." : TONE_LINE[tone];
  const top = result.top.slice(0, 3);

  return (
    <>
      <section className="fixed inset-x-0 top-[24vh] z-20 flex flex-col items-center px-5 text-center md:pr-48" aria-live="polite">
        {result.golden && <img src="/krill.png" alt="" width={72} height={72} className="pixel sprite mb-3 animate-bob" />}
        <h1 className={`animate-surface font-pixel text-[clamp(2.5rem,9vw,5rem)] font-bold uppercase leading-none tracking-wide ${TONE_TEXT[tone]}`}>
          {TONE_LABEL[tone]}
        </h1>
        {said && <p className="mt-5 font-pixel text-2xl text-ink sm:text-3xl">“{said}”</p>}
        <p className="mt-4 font-pixel text-xl tabular-nums sm:text-2xl">
          <span className="text-mist">+{result.points} pts</span>
          <span className="mx-3 text-slate">·</span>
          <span className="text-ink">sink {meters(result.points * mpp)}</span>
        </p>
        <p className="mt-3 text-sm text-mist">
          {line}
          {result.valid && ` ${result.share_pct}% of divers said it.`}
        </p>

        <div className="mt-8 w-full max-w-md space-y-2 text-left text-xs">
          {!result.golden && (
            <p className="text-mist">
              Golden Krill was hiding at <b className="font-medium text-gold">{result.golden_answer}</b>
            </p>
          )}
          {top.length > 0 && (
            <p className="text-slate">
              Most said:{" "}
              {top.map((t, i) => (
                <span key={t.answer} className={t.answer === result.answer ? "text-sonar" : "text-mist"}>
                  {i > 0 && " · "}
                  {t.answer} {t.pct}%
                </span>
              ))}
            </p>
          )}
        </div>
      </section>

      <div className="fixed inset-x-0 bottom-0 z-30 flex justify-center px-5 pb-8 md:pr-48">
        <PixelButton onClick={onNext} autoFocus variant="ghost" className="min-w-64 border-sonar! py-4! tracking-[0.3em]!">
          {last ? "Surface ▲" : "Descend ▼"}
        </PixelButton>
      </div>
    </>
  );
}
