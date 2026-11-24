"use client";

import type { CSSProperties } from "react";
import type { GuessResult } from "../lib/api";
import { CREATURE, dropOf, meters, TONE_LABEL, TONE_TEXT, toneOf, type Tone } from "../lib/game";
import { sinkMs, verdictMs } from "../lib/useDive";

// How hard each tier celebrates, in its creature's colours: particle burst, sonar rings, glow.
// `colors` alternate across the particles (perch teal + yellow, anglerfish purple + neon cyan, ...).
type Fx = { particles: number; reach: number; colors: string[]; rings: number; glow: string; scale: number; sprite: number };
const FX: Record<Tone, Fx> = {
  common: { particles: 6, reach: 60, colors: ["var(--color-alewife)"], rings: 0, glow: "transparent", scale: 1, sprite: 150 },
  uncommon: { particles: 12, reach: 95, colors: ["var(--color-perch)", "var(--color-perch-fin)"], rings: 1, glow: "rgba(60,198,180,0.18)", scale: 1.05, sprite: 160 },
  rare: { particles: 18, reach: 140, colors: ["var(--color-rare)", "#ffa3a3"], rings: 2, glow: "rgba(234,74,79,0.28)", scale: 1.12, sprite: 260 },
  deepcut: { particles: 26, reach: 190, colors: ["var(--color-deep)", "var(--color-neon)"], rings: 3, glow: "rgba(111,47,208,0.45)", scale: 1.2, sprite: 190 },
  golden: { particles: 38, reach: 260, colors: ["var(--color-gold)", "#ffffff", "var(--color-uoft)"], rings: 3, glow: "rgba(232,184,74,0.45)", scale: 1.3, sprite: 200 },
  miss: { particles: 0, reach: 0, colors: ["var(--color-slate)"], rings: 0, glow: "transparent", scale: 1, sprite: 0 },
};

/**
 * The verdict between prompts, scaled to the tier: Common gets a few bubbles, Deep Cut a
 * bioluminescent burst with sonar rings and a jolt, One in a Krillion a full golden bloom.
 */
export function Flash({ result }: { result: GuessResult }) {
  const tone = toneOf(result);
  const fx = FX[tone];
  const creature = CREATURE[tone];
  const label = TONE_LABEL[tone];
  const ms = verdictMs(result);
  const timed = (extra: CSSProperties = {}): CSSProperties => ({ animationDuration: `${ms}ms`, ...extra });

  return (
    <div
      className={`pointer-events-none fixed inset-0 z-20 ${tone === "deepcut" || tone === "golden" ? "animate-jolt" : ""}`}
      style={{ animationDelay: `${sinkMs(result)}ms` }}
      role="status"
      aria-live="polite"
    >
      {/* Tinted wash: coral for a miss, the tier's glow otherwise */}
      <div
        className="absolute inset-0 animate-wash"
        style={timed({
          background:
            tone === "miss"
              ? "radial-gradient(ellipse at center, transparent 40%, rgba(40,48,70,0.4))"
              : `radial-gradient(circle at 50% 38%, ${fx.glow}, transparent 60%)`,
        })}
      />

      {/* One in a Krillion: slow golden rays behind everything */}
      {tone === "golden" && (
        <div
          className="absolute left-1/2 top-[38%] size-[140vmax] -translate-x-1/2 -translate-y-1/2 animate-rays opacity-0"
          style={timed({
            background:
              "repeating-conic-gradient(from 0deg, rgba(232,184,74,0.16) 0deg 8deg, transparent 8deg 24deg)",
            maskImage: "radial-gradient(circle, #000 0%, transparent 45%)",
          })}
        />
      )}

      <div className="absolute left-1/2 top-[38%]">
        {/* Sonar rings */}
        {Array.from({ length: fx.rings }, (_, i) => (
          <span
            key={i}
            className="absolute left-0 top-0 size-24 rounded-full border-2 animate-ring"
            style={{ borderColor: fx.colors[i % fx.colors.length], animationDelay: `${i * 160}ms` }}
          />
        ))}
        {/* Particle burst: bubbles for low tiers, glowing plankton and gold flecks higher up */}
        {Array.from({ length: fx.particles }, (_, i) => {
          const angle = (i / fx.particles) * Math.PI * 2 + (i % 2) * 0.3;
          const dist = fx.reach * (0.6 + ((i * 37) % 40) / 100);
          const color = fx.colors[i % fx.colors.length];
          return (
            <span
              key={i}
              className={`absolute left-0 top-0 animate-burst ${tone === "common" || tone === "uncommon" ? "rounded-full border" : ""}`}
              style={
                {
                  width: 3 + (i % 3) * 2,
                  height: 3 + (i % 3) * 2,
                  background: tone === "common" || tone === "uncommon" ? "transparent" : color,
                  borderColor: color,
                  boxShadow: tone === "deepcut" || tone === "golden" ? `0 0 8px ${color}` : undefined,
                  "--dx": `${Math.cos(angle) * dist}px`,
                  "--dy": `${Math.sin(angle) * dist - (tone === "common" ? 40 : 0)}px`,
                  animationDelay: `${(i % 5) * 30}ms`,
                } as CSSProperties
              }
            />
          );
        })}
      </div>

      {/* The verdict itself */}
      <div className="absolute inset-x-0 top-[30vh] flex justify-center px-5">
        <div className="animate-flash text-center" style={timed()}>
          {creature && (
            <div className="animate-float [animation-duration:2.4s]">
            <img
              src={creature.src}
              alt=""
              className={`mx-auto mb-4 h-auto ${tone === "golden" ? "animate-krill-spin" : "animate-swim-in"}`}
              style={{ width: fx.sprite, filter: tone === "deepcut" ? "drop-shadow(0 0 12px var(--color-neon))" : tone === "golden" ? "drop-shadow(0 0 14px rgba(232,184,74,0.7))" : undefined }}
            />
            </div>
          )}
          <div
            className={`font-pixel text-[clamp(2.5rem,9vw,5rem)] font-bold uppercase leading-none tracking-wide ${TONE_TEXT[tone]} ${tone === "miss" ? "animate-shake" : ""}`}
            style={{
              transform: `scale(${fx.scale})`,
              textShadow: tone === "deepcut" || tone === "golden" ? `0 0 24px ${fx.colors[tone === "deepcut" ? 1 : 0]}` : undefined,
            }}
          >
            {label}
          </div>
          {creature && <div className="mt-3 text-sm uppercase tracking-[0.3em] text-ink/80">{creature.name}</div>}
          <div className="mt-3 font-pixel text-3xl tabular-nums text-ink animate-count sm:text-4xl">
            +{result.points}
            {result.points > 0 && <span className="ml-4 text-sonar">▼ {meters(dropOf(result))}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
