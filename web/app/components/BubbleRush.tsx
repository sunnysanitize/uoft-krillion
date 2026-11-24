// Bubbles of all sizes streaming up past the camera as it plunges.
const BUBBLES = Array.from({ length: 60 }, (_, i) => ({
  left: (i * 37) % 100,
  size: 4 + ((i * 7) % 5) * 4,
  delay: ((i * 13) % 10) * 0.06,
  duration: 0.9 + ((i * 11) % 6) * 0.12,
}));

/** `count` bubbles stream past over about `ms`: a few quick ones for a short drop, a long torrent for a deep one. */
export function BubbleRush({ count = 48, ms = 1800 }: { count?: number; ms?: number }) {
  const stretch = ms / 1800;
  return (
    <div className="pointer-events-none fixed inset-0 z-10 overflow-hidden" aria-hidden>
      {BUBBLES.slice(0, count).map((b, i) => (
        <span
          key={i}
          className="absolute rounded-full border-2 border-foam/70 bg-foam/10 will-change-transform"
          style={{
            left: `${b.left}%`,
            bottom: -40,
            width: b.size,
            height: b.size,
            animation: `rush ${b.duration * stretch}s cubic-bezier(.3,0,.7,1) ${b.delay * stretch}s both`,
          }}
        />
      ))}
    </div>
  );
}
