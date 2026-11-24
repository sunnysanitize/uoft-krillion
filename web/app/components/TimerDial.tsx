const R = 26;
const C = 2 * Math.PI * R;

/** Air gauge: a stepped ring that drains, turning coral for the last five seconds. */
export function TimerDial({ remaining, limit }: { remaining: number; limit: number }) {
  const secs = Math.ceil(remaining / 1000);
  const urgent = remaining <= 5000;
  // Quantise to 40 steps so the ring ticks like a gauge rather than gliding.
  const frac = Math.ceil((remaining / limit) * 40) / 40;
  return (
    <div
      className="relative grid size-16 shrink-0 place-items-center"
      role="timer"
      aria-label={`${secs} seconds of air left`}
    >
      <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx="32" cy="32" r={R} fill="none" stroke="var(--color-line)" strokeWidth="6" />
        <circle
          cx="32"
          cy="32"
          r={R}
          fill="none"
          stroke={urgent ? "var(--color-coral)" : "var(--color-sonar)"}
          strokeWidth="6"
          strokeDasharray={`${C * frac} ${C}`}
          shapeRendering="crispEdges"
        />
      </svg>
      <span className={`font-pixel text-2xl tabular-nums ${urgent ? "text-coral" : "text-ink"}`}>{secs}</span>
    </div>
  );
}
