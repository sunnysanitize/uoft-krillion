// Pixel sea life fixed at depths in the water, so it scrolls past as you sink. All values are
// whole numbers so the server's HTML and the browser agree exactly.

/** A jellyfish: the bell squeezes to push it up, then it sinks back, tentacles trailing. */
export function Jellyfish({ glow, size = 40, delay = 0 }: { glow?: string; size?: number; delay?: number }) {
  const color = glow ?? "#f4b6d6";
  return (
    <div
      className="animate-jelly will-change-transform"
      style={{ filter: glow ? `drop-shadow(0 0 8px ${glow})` : undefined, animationDelay: `${delay}s` }}
    >
      <svg viewBox="0 0 12 16" style={{ width: size }} shapeRendering="crispEdges" opacity={glow ? 0.9 : 0.75}>
        <g className="animate-bell" style={{ transformBox: "fill-box", transformOrigin: "50% 0%", animationDelay: `${delay}s` }}>
          <path d="M3 0h6v1h2v1h1v3h-12v-3h1v-1h2z" fill={color} />
          <path d="M4 1h2v1h-2zM2 2h1v1h-1z" fill="#ffffff" opacity="0.6" />
          <path d="M0 5h12v1h-12z" fill={color} opacity="0.6" />
        </g>
        <path d="M2 6h1v3h1v3h-1v2h-1zM5 6h1v4h-1v3h1v2h-1zM8 6h1v2h1v4h-1v3h-1zM10 6h1v3h-1z" fill={color} opacity="0.55" />
      </svg>
    </div>
  );
}

/** A green sea turtle, paddling. */
export function Turtle() {
  return (
    <svg viewBox="0 0 16 10" className="w-16 animate-float [animation-duration:4s]" shapeRendering="crispEdges">
      <path d="M4 0h3v2h-2v1h-1zM4 8h1v1h2v1h-3zM11 0h2v2h-1v-1h-1zM11 9h2v1h-2z" fill="#8fbf7a" />
      <path d="M5 2h6v1h2v1h1v3h-1v1h-2v1h-6v-1h-2v-1h-1v-3h1v-1h2z" fill="#3d7a4a" />
      <path d="M6 3h2v2h-2zM9 3h2v2h-2zM7 5h3v2h-3z" fill="#5c9a5e" />
      <path d="M14 4h2v2h-2z" fill="#8fbf7a" />
      <path d="M15 4h1v1h-1z" fill="#1a2a1a" />
    </svg>
  );
}

/** A whale, far off: a huge dim silhouette with a pale belly. */
export function Whale() {
  return (
    <svg viewBox="0 0 48 16" className="w-[34rem] opacity-30" shapeRendering="crispEdges">
      <path
        d="M0 7h3v-1h3v-1h3v-1h4v-1h14v1h6v1h3v1h2v1h2v1h1v-2h2v-2h2v-1h2v3h-1v2h-1v1h1v2h1v3h-2v-1h-2v-2h-2v-1h-1v1h-2v1h-3v1h-6v1h-14v-1h-4v-1h-3v-1h-3z"
        fill="#0b2c55"
      />
      <path d="M6 9h20v1h-4v1h-12v-1h-4z" fill="#2a5a8c" />
      <path d="M9 6h1v1h-1z" fill="#cfe6f5" />
      <path d="M16 10h4v2h-1v1h-2v-1h-1z" fill="#0b2c55" />
    </svg>
  );
}

const VENT = [0, 1, 2, 3, 4, 5, 6, 7];

// Stable pseudo-random 0..1, so the plankton scatter is the same on the server and in the browser.
const hash = (n: number) => {
  const v = Math.sin(n * 127.1) * 43758.5453;
  return v - Math.floor(v);
};
// Specks scattered densest at the centre of the cloud, thinning out to its edge (whole px).
const SPECKS = Array.from({ length: 28 }, (_, i) => {
  const angle = hash(i) * Math.PI * 2;
  const r = Math.sqrt(hash(i + 100)) * 90 * (0.4 + hash(i + 200) * 0.6);
  return { x: Math.round(96 + Math.cos(angle) * r), y: Math.round(96 + Math.sin(angle) * r * 0.7), size: 2 + (i % 3) };
});

/** A column of bubbles streaming up from a vent below. */
export function BubbleColumn() {
  return (
    <div className="relative h-72 w-6">
      {VENT.map((i) => (
        <span
          key={i}
          className="absolute bottom-0 rounded-full border border-foam/70 bg-foam/10 animate-vent will-change-transform"
          style={{ left: (i * 5) % 14, width: 4 + (i % 3) * 3, height: 4 + (i % 3) * 3, animationDelay: `${-i * 0.45}s` }}
        />
      ))}
    </div>
  );
}

/** A cloud of bioluminescent plankton, twinkling in the dark. */
export function Glow({ color }: { color: string }) {
  return (
    <div className="relative size-48">
      {SPECKS.map((p, i) => (
        <span
          key={i}
          className="absolute rounded-full animate-twinkle"
          style={{
            left: p.x,
            top: p.y,
            width: p.size,
            height: p.size,
            background: color,
            boxShadow: `0 0 6px ${color}`,
            animationDelay: `${-((i * 7) % 40) / 10}s`,
            animationDuration: `${2 + (i % 4)}s`,
          }}
        />
      ))}
    </div>
  );
}
