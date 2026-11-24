import { meters, Zone } from "../lib/game";

const PX_PER_M = 0.5;
const SPAN = 15000; // deepest reachable is 7 prompts x (100 + 100 bonus) x 10 m = 14,000 m
const TICKS = Array.from({ length: SPAN / 100 + 1 }, (_, i) => i * 100);

/**
 * Right-edge sonar ruler. The strip slides so the diver marker stays fixed
 * at 40% of the height; campus zone boundaries are named on the scale.
 */
export function DepthRuler({ depth, zones }: { depth: number; zones: Zone[] }) {
  const zoneAt = new Map(zones.map((z) => [z.start, z.name]));
  return (
    <aside
      className="pointer-events-none fixed inset-y-0 right-0 z-10 hidden w-44 overflow-hidden md:block"
      aria-label={`Depth ${meters(depth)}`}
    >
      <div className="absolute inset-y-0 right-12 w-0.5 bg-line" />
      <div
        className="absolute inset-x-0 top-[40%] transition-transform duration-[1600ms] ease-[cubic-bezier(.3,.7,.2,1)]"
        style={{ transform: `translateY(${-depth * PX_PER_M}px)` }}
      >
        {TICKS.map((m) => {
          const major = m % 500 === 0;
          const zone = zoneAt.get(m);
          return (
            <div key={m} className="absolute right-12 flex items-center" style={{ top: m * PX_PER_M }}>
              {(major || zone) && (
                <span className={`mr-2 -translate-y-1/2 text-right text-[10px] leading-tight ${zone ? "text-sonar" : "text-slate"}`}>
                  {zone ? (
                    <>
                      <span className="block uppercase tracking-[0.2em]">{zone}</span>
                      <span className="text-slate">{m.toLocaleString("en-CA")}</span>
                    </>
                  ) : (
                    m.toLocaleString("en-CA")
                  )}
                </span>
              )}
              <span className={`h-0.5 -translate-y-1/2 ${zone ? "w-4 bg-sonar" : major ? "w-3 bg-mist" : "w-1.5 bg-slate"}`} />
            </div>
          );
        })}
      </div>
      {/* Diver marker stays put on the far side of the rail; the water moves past it. */}
      <div className="absolute right-0 top-[40%] flex w-12 -translate-y-1/2 items-center">
        <span className="h-0.5 w-3 bg-gold" />
        <img src="/krill.png" alt="" width={28} height={28} className="pixel sprite rotate-90" />
      </div>
    </aside>
  );
}
