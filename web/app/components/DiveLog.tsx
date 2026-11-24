import type { GuessResult } from "../lib/api";
import { TONE_LABEL, toneOf, type Tone } from "../lib/game";

// SVG fills need raw values; these mirror the tone tokens in globals.css.
const FILL: Record<Tone, string> = {
  golden: "var(--color-gold)",
  legendary: "var(--color-gold)",
  rare: "var(--color-sonar)",
  uncommon: "var(--color-foam)",
  common: "var(--color-mist)",
  basic: "var(--color-slate)",
  miss: "var(--color-coral)",
};

const W = 700;
const H = 220;
const PAD = { l: 44, r: 12, t: 12, b: 28 };

/** Metres gained on each prompt, drawn as drop lines from the surface. Deeper = rarer. */
export function DiveLog({ results, mpp, prompts }: { results: GuessResult[]; mpp: number; prompts: string[] }) {
  const gains = results.map((r) => r.points * mpp);
  const top = Math.max(1000, Math.ceil(Math.max(...gains, 0) / 500) * 500);
  const x = (i: number) => PAD.l + ((i + 0.5) * (W - PAD.l - PAD.r)) / results.length;
  const y = (m: number) => PAD.t + (m / top) * (H - PAD.t - PAD.b);
  const grid = Array.from({ length: top / 500 + 1 }, (_, i) => i * 500);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Metres gained on each prompt">
      {grid.map((m) => (
        <g key={m}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(m)} y2={y(m)} stroke="var(--color-line)" strokeDasharray="2 4" />
          <text x={PAD.l - 8} y={y(m) + 3} textAnchor="end" fontSize="10" fill="var(--color-slate)">
            {m === 0 ? "0 m" : `-${m.toLocaleString("en-CA")}`}
          </text>
        </g>
      ))}
      {results.map((r, i) => {
        const tone = toneOf(r);
        const m = gains[i];
        return (
          <g key={i}>
            <title>{`${i + 1}. ${prompts[i] ?? ""}: ${r.answer ?? "no answer"} (${TONE_LABEL[tone]}, ${m} m)`}</title>
            <line x1={x(i)} x2={x(i)} y1={y(0)} y2={y(m)} stroke={FILL[tone]} strokeWidth="2" opacity="0.6" />
            <rect x={x(i) - 6} y={y(m) - 6} width="12" height="12" fill={FILL[tone]} shapeRendering="crispEdges" />
            <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--color-mist)">
              {i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
