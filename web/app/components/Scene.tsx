import { Cloud } from "./Cloud";
import { BubbleColumn, Glow, Jellyfish, Turtle, Whale } from "./SeaLife";
import { Water } from "./Water";

// The waterline sits this far down the screen on the title shot...
const SURFACE_VH = 64;
// ...and this far down once the dive starts.
const DIVE_VH = 26;
// How far the world is stretched vertically: big drops travel a long way. Camera travel per metre,
// world positions and the water's colour bands all scale with it, so depths in metres stay put.
const STRETCH = 1.875;
const PX_PER_M = 0.32 * STRETCH;
// Capped so the deepest dives still land on water.
const MAX_TRAVEL = 7000;

// The water's colour by depth: lake blue, darkening fast to indigo by ~1,000 m and near black by
// ~3,500 m. [colour, px below the waterline before stretching]
const WATER: [string, number][] = [
  ["#1f74a8", 0], ["#1a5c98", 180], ["#1d468a", 380], ["#24327a", 600], ["#241f5e", 850],
  ["#1a1242", 1100], ["#0e0926", 1400], ["#07051a", 1800], ["#030210", 2400],
];
const WATER_GRADIENT = `linear-gradient(180deg,${WATER.map(([c, px]) => `${c} ${Math.round(px * STRETCH)}px`).join(",")})`;
// The ruins layer moves at this fraction of the camera, so it reads as far away.
const FAR_PARALLAX = 0.5;
// The camera's sink takes --sink (set per drop by the page); everything that rides it follows.
const CAMERA_EASE = "duration-(--sink) ease-(--sink-ease)";

const SNOW = Array.from({ length: 36 }, (_, i) => ({
  left: (i * 53) % 100,
  size: i % 5 === 0 ? 3 : 2,
  delay: -((i * 1.7) % 18),
  duration: 14 + ((i * 7) % 12),
  opacity: 0.15 + ((i * 13) % 30) / 100,
}));

// A clear summer morning over Lake Ontario: deep blue overhead, hazy and warm at the horizon.
const MORNING = "linear-gradient(180deg,#3f9be0 0%,#6db6ea 35%,#a9d6f3 68%,#e4f1f6 88%,#fbeed2 100%)";

// A Toronto July sky, held still and kept clear of the title: [shape, left %, top %, pixel size].
const CLOUDS: [number, number, number, number][] = [
  [0, 3, 6, 5],
  [1, 72, 4, 5],
  [3, 24, 36, 4],
  [2, 62, 42, 4],
  [3, 89, 26, 3],
  [1, 42, 60, 3],
];

// Gulls gliding across: [top %, seconds to cross, start offset seconds].
const GULLS: [number, number, number][] = [
  [30, 38, -5],
  [34, 44, -12],
  [22, 60, -35],
];

// Fish schools: [px below the waterline, size, swim seconds, start offset, leftward].
const SCHOOLS: [number, number, number, number, boolean][] = [
  [120, 3, 38, -6, false],
  [430, 4, 52, -30, true],
  [820, 3, 44, -12, false],
  [1250, 5, 64, -40, true],
  [1750, 3, 48, -22, false],
  [2250, 4, 70, -50, true],
];

// Sunken campus on the far layer: [left %, px below the waterline, which silhouette].
const RUINS: [number, number, "arch" | "column" | "dome"][] = [
  [8, 520, "arch"],
  [74, 760, "column"],
  [30, 1150, "dome"],
  [84, 1500, "arch"],
  [12, 1900, "column"],
  [58, 2300, "dome"],
];

// Jellyfish: [left %, px below the waterline, size px, glow colour for the deep ones].
const JELLIES: [number, number, number, string | undefined][] = [
  [26, 520, 36, undefined],
  [82, 690, 44, undefined],
  [60, 980, 30, undefined],
  [18, 1500, 44, "#3fe0ff"],
  [76, 1760, 36, "#b07cff"],
  [42, 2100, 52, "#3fe0ff"],
  [88, 2360, 40, "#b07cff"],
];
// Bubble vents: [left %, px below the waterline].
const VENTS: [number, number][] = [
  [30, 1150],
  [70, 1900],
];
// Bioluminescent clouds: [left %, px below the waterline, colour].
const GLOWS: [number, number, string][] = [
  [22, 1850, "#3fe0ff"],
  [66, 2250, "#b07cff"],
  [46, 2600, "#7dffd0"],
];

const KELP = [
  { left: 2, h: 150, delay: 0 },
  { left: 6, h: 100, delay: -1.3 },
  { left: 90, h: 170, delay: -0.6 },
  { left: 95, h: 120, delay: -2.1 },
  { left: 47, h: 70, delay: -1.7 },
];

const BUBBLES = Array.from({ length: 7 }, (_, i) => ({ dx: (i * 5) % 14, delay: -i * 0.9, duration: 5 + (i % 3) }));

/**
 * One continuous world: a summer sky, a live waterline with a sailboat, then water that
 * darkens with depth. The camera (a translate on the world) sinks as the dive goes on;
 * a far layer of sunken campus moves slower for depth, and the bathysphere rides along.
 */
export function Scene({
  mode,
  depth,
  ping = 0,
  sink = 1800,
  ease = "cubic-bezier(.45,.05,.2,1)",
}: {
  mode: "surface" | "dive";
  depth: number;
  ping?: number;
  sink?: number;
  ease?: string;
}) {
  const diving = mode === "dive";
  // Written out flat for each layer: a nested calc() times a factor can't be animated, so it would jump.
  const camera = (k: number) =>
    diving ? `calc(${-(SURFACE_VH - DIVE_VH) * k}vh - ${Math.min(depth * PX_PER_M, MAX_TRAVEL) * k}px)` : "0px";
  const travel = camera(1);
  const below = (px: number) => `calc(${SURFACE_VH}vh + ${Math.round(px * STRETCH)}px)`;

  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-abyss" style={{ "--sink": `${sink}ms`, "--sink-ease": ease } as React.CSSProperties} aria-hidden>
      {/* The whole world rocks slowly, like riding the swell */}
      <div className="absolute inset-0 animate-roll will-change-transform">
      {/* Near world: sky, waterline, water */}
      <div className={`absolute inset-x-0 top-0 transition-transform will-change-transform ${CAMERA_EASE}`} style={{ transform: `translate3d(0, ${travel}, 0)` }}>
        <div
          className="relative flex flex-col justify-end overflow-hidden"
          style={{ height: `${SURFACE_VH}vh`, background: MORNING }}
        >
          <Sun />
          {CLOUDS.map(([shape, left, top, pixel], i) => (
            <Cloud key={i} shape={shape} left={left} top={top} pixel={pixel} />
          ))}
          {GULLS.map(([top, secs, offset], i) => (
            <Gull key={i} top={top} seconds={secs} offset={offset} />
          ))}
        </div>
        <Water />
        <div
          style={{
            height: `calc(100vh + ${MAX_TRAVEL + 200}px)`,
            background: WATER_GRADIENT,
          }}
        />
      </div>

      {/* Far layer: the sunken campus, drifting by at half speed */}
      <div
        className={`parallax-far absolute inset-x-0 top-0 transition-transform will-change-transform ${CAMERA_EASE}`}
        style={{ transform: `translate3d(0, ${camera(FAR_PARALLAX)}, 0)` }}
      >
        {RUINS.map(([left, px, kind], i) => (
          <Ruin key={i} kind={kind} style={{ left: `${left}%`, top: below(px * FAR_PARALLAX + 260) }} />
        ))}
        {/* a whale gliding past in the distance */}
        <div className="absolute left-0 animate-swim [animation-direction:reverse] [animation-duration:150s]" style={{ top: below(1000) }}>
          <Whale />
        </div>
      </div>

      {/* Fish swim at fixed depths, so they scroll past with the camera */}
      <div className={`parallax-mid absolute inset-x-0 top-0 transition-transform will-change-transform ${CAMERA_EASE}`} style={{ transform: `translate3d(0, ${travel}, 0)` }}>
        {SCHOOLS.map(([px, n, secs, offset, left], i) => (
          <School key={i} top={below(px)} count={n} seconds={secs} offset={offset} leftward={left} />
        ))}
        {/* a turtle paddling across the shallows */}
        <div className="absolute left-0 animate-swim [animation-duration:85s] [animation-delay:-30s]" style={{ top: below(260) }}>
          <Turtle />
        </div>
        {JELLIES.map(([left, px, size, glow], i) => (
          <div key={i} className="absolute" style={{ left: `${left}%`, top: below(px) }}>
            <Jellyfish size={size} glow={glow} delay={-i * 1.7} />
          </div>
        ))}
        {VENTS.map(([left, px], i) => (
          <div key={i} className="absolute" style={{ left: `${left}%`, top: below(px) }}>
            <BubbleColumn />
          </div>
        ))}
        {GLOWS.map(([left, px, color], i) => (
          <div key={i} className="absolute" style={{ left: `${left}%`, top: below(px) }}>
            <Glow color={color} />
          </div>
        ))}
      </div>

      {/* Marine snow drifts in screen space so it reads at every depth. */}
      {SNOW.map((s, i) => (
        <span
          key={i}
          className="absolute top-0 bg-foam animate-snow transition-opacity duration-1000 will-change-transform"
          style={{
            left: `${s.left}%`,
            width: s.size,
            height: s.size,
            opacity: diving ? s.opacity : 0,
            animationDelay: `${s.delay}s`,
            animationDuration: `${s.duration}s`,
          }}
        />
      ))}

      {/* Foreground kelp, only once we're under */}
      <div className={`parallax-near absolute -inset-x-8 bottom-0 transition-opacity duration-1000 ${diving ? "opacity-100" : "opacity-0"}`}>
        {KELP.map((k, i) => (
          <Kelp key={i} left={k.left} height={k.h} delay={k.delay} />
        ))}
      </div>

      <div className="parallax-mid absolute inset-0">
        <Bathysphere diving={diving} ping={ping} />
      </div>
      </div>
    </div>
  );
}

/** The morning sun, low in the east, with a bright haze around it. */
function Sun() {
  return (
    <div className="absolute bottom-[26%] left-[14%] -translate-x-1/2">
      <div className="absolute left-1/2 top-1/2 size-[30rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(255,250,225,0.75),rgba(255,236,180,0.25)_35%,transparent_65%)]" />
      <svg viewBox="0 0 12 12" className="relative w-20" shapeRendering="crispEdges">
        <path d="M4 0h4v1h2v1h1v2h1v4h-1v2h-1v1h-2v1h-4v-1h-2v-1h-1v-2h-1v-4h1v-2h1v-1h2z" fill="#fff6d0" />
        <path d="M4 1h3v1h-3zM2 3h2v1h-2z" fill="#ffffff" />
      </svg>
    </div>
  );
}

/** A gull gliding across, flapping now and then. */
function Gull({ top, seconds, offset }: { top: number; seconds: number; offset: number }) {
  return (
    <div className="absolute left-0 animate-drift" style={{ top: `${top}%`, animationDuration: `${seconds}s`, animationDelay: `${offset}s` }}>
      <svg viewBox="0 0 11 4" className="w-6 animate-flap" shapeRendering="crispEdges">
        <path d="M0 1h1v1h2v1h2v-1h1v1h2v-1h2v-1h1v1h-1v1h-2v1h-2v-1h-1v1h-2v-1h-2v-1h-1z" fill="#3a4a5e" />
      </svg>
    </div>
  );
}

function Ruin({ kind, style }: { kind: "arch" | "column" | "dome"; style: React.CSSProperties }) {
  const shapes = {
    // a collapsed gothic arch, like a drowned Hart House cloister
    arch: "M0 40v-24h2v-6h2v-4h2v-2h2v-2h8v2h2v2h2v4h2v6h2v24h-6v-20h-1v-3h-2v-2h-6v2h-2v3h-1v20z",
    // a broken column with its capital
    column: "M4 40v-30h-2v-3h12v3h-2v30zM2 7v-3h4v-1h2v1h6v3z",
    // half a dome, like a sunken Convocation Hall
    dome: "M0 40v-12h2v-4h2v-3h3v-2h4v-1h8v1h4v2h3v3h2v4h2v12h-6v-8h-4v8h-6v-8h-4v8z",
  };
  return (
    <svg viewBox="0 0 32 40" className="absolute w-24 opacity-25 sm:w-32" style={style} shapeRendering="crispEdges">
      <path d={shapes[kind]} fill="#0a2448" />
    </svg>
  );
}

function School({ top, count, seconds, offset, leftward }: { top: string; count: number; seconds: number; offset: number; leftward: boolean }) {
  return (
    <div
      className="absolute left-0 animate-swim"
      style={{ top, animationDuration: `${seconds}s`, animationDelay: `${offset}s`, animationDirection: leftward ? "reverse" : "normal" }}
    >
      <div className={leftward ? "-scale-x-100" : ""}>
        {Array.from({ length: count }, (_, i) => (
          <svg
            key={i}
            viewBox="0 0 8 5"
            className="absolute w-4 animate-float"
            style={{ left: (i * 23) % 60, top: (i * 11) % 28, animationDelay: `${-i * 0.4}s` }}
            shapeRendering="crispEdges"
          >
            <path d="M2 1h3v1h1v1h-1v1h-3v-1h-1v1h-1v-3h1v1h1z" fill="#3c7fa8" />
            <path d="M5 2h1v1h-1z" fill="#a9d8ee" />
          </svg>
        ))}
      </div>
    </div>
  );
}

function Kelp({ left, height, delay }: { left: number; height: number; delay: number }) {
  return (
    <svg
      viewBox="0 0 8 40"
      preserveAspectRatio="none"
      className="absolute bottom-0 w-5 origin-bottom animate-sway opacity-50"
      style={{ left: `${left}%`, height, animationDelay: `${delay}s` }}
      shapeRendering="crispEdges"
    >
      <path d="M3 40v-8h-1v-6h1v-6h1v-6h-1v-6h1v-8h2v8h1v6h-1v6h-1v6h1v6h-1v8z" fill="#0d3b3a" />
      <path d="M1 30h2v2h-2zM5 18h2v2h-2zM1 8h2v2h-2z" fill="#14524c" />
    </svg>
  );
}

/** The player's bathysphere: bobs at the surface on the title shot, then rides the dive on its tether. */
function Bathysphere({ diving, ping }: { diving: boolean; ping: number }) {
  return (
    <div
      className={`absolute left-[7%] transition-[top] ${CAMERA_EASE} sm:left-[12%]`}
      style={{ top: diving ? "44vh" : `calc(${SURFACE_VH}vh - 54px)` }}
    >
      {/* tether up to the surface, paid out once we dive */}
      <div
        className={`absolute bottom-full left-1/2 h-[100vh] w-px -translate-x-1/2 bg-mist/40 transition-opacity duration-1000 ${diving ? "opacity-100" : "opacity-0"}`}
      />
      <div className="relative animate-float">
        <svg viewBox="0 0 14 14" className="w-10 sm:w-12" shapeRendering="crispEdges">
          <path d="M5 0h4v1h2v1h1v1h1v2h1v4h-1v2h-1v1h-1v1h-2v1h-4v-1h-2v-1h-1v-1h-1v-2h-1v-4h1v-2h1v-1h1v-1h2z" fill="#3a4f6e" />
          <path d="M5 1h4v1h-4z" fill="#6d85a8" />
          <path d="M5 4h4v1h1v4h-1v1h-4v-1h-1v-4h1z" fill="#e8b84a" />
          <path d="M5 5h2v2h-2z" fill="#fff3c4" />
        </svg>
        {/* porthole light cone */}
        <div
          className={`pointer-events-none absolute left-1/2 top-1/2 h-40 w-28 -translate-x-1/2 transition-opacity duration-1000 ${diving ? "opacity-100" : "opacity-0"}`}
          style={{ background: "radial-gradient(ellipse at top, rgba(232,184,74,0.18), transparent 70%)" }}
        />
        {/* sonar ping on every new prompt */}
        {diving && <span key={ping} className="absolute left-1/2 top-1/2 size-10 border border-sonar animate-ping-ring" />}
        {diving &&
          BUBBLES.map((b, i) => (
            <span
              key={i}
              className="absolute bottom-full size-1 bg-foam/70 animate-rise will-change-transform"
              style={{ left: 18 + b.dx, animationDelay: `${b.delay}s`, animationDuration: `${b.duration}s` }}
            />
          ))}
      </div>
    </div>
  );
}

export const SCENE = { SURFACE_VH, DIVE_VH };
