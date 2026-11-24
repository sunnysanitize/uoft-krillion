import { Skyline } from "./Skyline";

// The waterline sits this far down the screen on the title shot...
const SURFACE_VH = 64;
// ...and this far down once the dive starts.
const DIVE_VH = 26;
// Camera travel per metre, capped so the deepest dives still land on water.
const PX_PER_M = 0.16;
const MAX_TRAVEL = 2200;

const SNOW = Array.from({ length: 36 }, (_, i) => ({
  left: (i * 53) % 100,
  size: i % 5 === 0 ? 3 : 2,
  delay: -((i * 1.7) % 18),
  duration: 14 + ((i * 7) % 12),
  opacity: 0.15 + ((i * 13) % 30) / 100,
}));

const STARS = [
  [6, 18], [14, 42], [22, 26], [31, 10], [38, 48], [47, 22], [55, 38], [63, 14], [71, 44], [79, 30], [86, 8], [93, 36],
];

/**
 * One continuous world: dusk sky over St. George, the waterline, then water that
 * darkens with depth. The camera (a translate on the world) sinks as you score.
 */
export function Scene({ mode, depth }: { mode: "surface" | "dive"; depth: number }) {
  const travel = mode === "surface" ? "0px" : `calc(-${SURFACE_VH - DIVE_VH}vh - ${Math.min(depth * PX_PER_M, MAX_TRAVEL)}px)`;
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-abyss" aria-hidden>
      <div
        className="absolute inset-x-0 top-0 transition-transform duration-[1800ms] ease-[cubic-bezier(.45,.05,.2,1)]"
        style={{ transform: `translateY(${travel})` }}
      >
        {/* Sky */}
        <div
          className="relative flex flex-col justify-end"
          style={{ height: `${SURFACE_VH}vh`, background: "linear-gradient(180deg,#040a16 0%,#0a1a36 62%,#13305a 100%)" }}
        >
          {STARS.map(([x, y], i) => (
            <span key={i} className="absolute size-0.5 bg-foam/60" style={{ left: `${x}%`, top: `${y}%` }} />
          ))}
          <Skyline className="relative mx-auto block w-full max-w-5xl" />
        </div>
        {/* Waterline: crest plus a stepped shimmer */}
        <div className="h-0.5 bg-sonar" />
        <div className="h-1 bg-[repeating-linear-gradient(90deg,var(--color-lightblue)_0_12px,transparent_12px_20px)] opacity-60" />
        {/* Water */}
        <div
          style={{
            height: `calc(100vh + ${MAX_TRAVEL + 200}px)`,
            background:
              "linear-gradient(180deg,#14507c 0px,#0f3f69 260px,#0b2c54 800px,#081b39 1500px,#050e22 2100px,#040a16 2600px)",
          }}
        />
      </div>

      {/* Marine snow drifts in screen space so it reads at every depth. */}
      {SNOW.map((s, i) => (
        <span
          key={i}
          className="absolute top-0 bg-foam animate-snow"
          style={{
            left: `${s.left}%`,
            width: s.size,
            height: s.size,
            opacity: mode === "surface" ? 0 : s.opacity,
            animationDelay: `${s.delay}s`,
            animationDuration: `${s.duration}s`,
          }}
        />
      ))}
    </div>
  );
}

export const SCENE = { SURFACE_VH, DIVE_VH };
