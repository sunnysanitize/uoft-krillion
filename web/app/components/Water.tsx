"use client";

import { useEffect, useRef } from "react";

/**
 * Gerstner (trochoidal) waves: each point of water moves in a circle, so the surface bunches
 * into sharp crests and stretches into long, flat troughs, unlike a plain sine. Several waves
 * of different length and speed add up, so sets build and fade instead of repeating.
 *
 * A wave is [amplitude px, wavenumber rad/px, speed rad/s, phase, steepness 0..1].
 */
type Wave = [amp: number, k: number, speed: number, phase: number, steep: number];
type Layer = { base: number; waves: Wave[]; top: string; bottom: string; foam: number };

// Back to front. The boat sits between the mid and front layers.
const BACK: Layer[] = [
  // far swell: long, low, hazy
  { base: 30, top: "rgba(140,200,232,0.65)", bottom: "rgba(70,150,200,0.65)", foam: 0,
    waves: [[5, 0.0075, 0.5, 0, 0.6], [2.5, 0.019, 0.85, 1.7, 0.5]] },
  // mid
  { base: 38, top: "rgba(80,165,214,0.95)", bottom: "rgba(40,120,175,0.95)", foam: 0.3,
    waves: [[7, 0.009, 0.75, 2.2, 0.75], [3, 0.022, 1.2, 0.5, 0.6], [1.5, 0.05, 2, 3.1, 0.4]] },
];
// front: steepest, with whitecaps; its bottom colour matches the water body below
const FRONT: Layer = { base: 50, top: "#3c97cc", bottom: "#1f74a8", foam: 1,
  waves: [[9, 0.0072, 0.9, 4.1, 0.85], [4, 0.017, 1.4, 1.1, 0.7], [2, 0.038, 2.2, 2.6, 0.5], [0.8, 0.085, 3, 0.3, 0.3]] };

const HEIGHT = 110;
const STEP = 3;
// How far up the boat sprite the waterline sits (0 = keel, 1 = masthead): the hull's lower edge.
const BOAT_WATERLINE = 0.16;

type Point = { x: number; y: number; crest: number };

/** Sample one layer's surface across the screen. `crest` runs 0 (trough) .. 1 (highest crest). */
function sample(layer: Layer, width: number, t: number): Point[] {
  const total = layer.waves.reduce((s, w) => s + w[0], 0);
  const pts: Point[] = [];
  for (let u = -40; u <= width + 40; u += STEP) {
    let x = u;
    let lift = 0;
    for (const [a, k, w, p, q] of layer.waves) {
      const theta = k * u - w * t + p;
      x -= q * a * Math.sin(theta) * 1.2;
      lift += a * Math.cos(theta);
    }
    pts.push({ x, y: layer.base - lift, crest: (lift / total + 1) / 2 });
  }
  return pts;
}

/** The surface height at screen x, interpolated between samples, and its slope. */
function surfaceAt(pts: Point[], x: number): { y: number; slope: number } {
  let i = pts.findIndex((p) => p.x >= x);
  if (i < 1) i = 1;
  const a = pts[i - 1];
  const b = pts[i];
  const y = a.y + ((x - a.x) / Math.max(0.5, b.x - a.x)) * (b.y - a.y);
  const l = pts[Math.max(0, i - 4)];
  const r = pts[Math.min(pts.length - 1, i + 4)];
  return { y, slope: (r.y - l.y) / Math.max(1, r.x - l.x) };
}

// Stable pseudo-random numbers so foam flecks and glints don't jump around between frames.
const hash = (n: number) => {
  const s = Math.sin(n * 127.1) * 43758.5453;
  return s - Math.floor(s);
};

function drawLayer(ctx: CanvasRenderingContext2D, layer: Layer, pts: Point[], seed: number) {
  const crestY = Math.min(...pts.map((p) => p.y));

  // Wave body, lit near the crests and darker in the troughs
  const grad = ctx.createLinearGradient(0, crestY, 0, layer.base + 14);
  grad.addColorStop(0, layer.top);
  grad.addColorStop(1, layer.bottom);
  ctx.beginPath();
  ctx.moveTo(pts[0].x, HEIGHT);
  for (const p of pts) ctx.lineTo(p.x, p.y);
  ctx.lineTo(pts[pts.length - 1].x, HEIGHT);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // A thin bright rim where the light catches each crest
  ctx.beginPath();
  pts.forEach((p, i) => ctx[i ? "lineTo" : "moveTo"](p.x, p.y + 0.5));
  ctx.strokeStyle = `rgba(210,236,250,${0.2 + layer.foam * 0.2})`;
  ctx.lineWidth = 1;
  ctx.stroke();

  if (!layer.foam) return;
  // Whitecaps: foam breaks along the highest crests and thins out as they drop
  for (let i = 1; i < pts.length; i++) {
    const cap = (pts[i].crest - 0.8) / 0.2;
    if (cap <= 0) continue;
    ctx.strokeStyle = `rgba(250,253,255,${Math.min(1, cap) * 0.9 * layer.foam})`;
    ctx.lineWidth = 1.5 + cap * 2;
    ctx.beginPath();
    ctx.moveTo(pts[i - 1].x, pts[i - 1].y + 1);
    ctx.lineTo(pts[i].x, pts[i].y + 1);
    ctx.stroke();
  }
  // Foam flecks trailing down the faces behind the crests
  for (let i = 0; i < pts.length; i += 2) {
    const p = pts[i];
    const r = hash(i + seed);
    if (p.crest < 0.55 || r > 0.35 * layer.foam) continue;
    ctx.fillStyle = `rgba(235,246,252,${(p.crest - 0.5) * 0.9})`;
    ctx.fillRect(p.x, p.y + 3 + r * 9, 1.5 + r * 2.5, 1);
  }
}

/**
 * The live waterline, redrawn every frame on two canvases with the sailboat between them:
 * back swells behind the boat, the front wave over its keel, so it floats in the water.
 */
export function Water({ boatAt = 0.34, sunAt = 0.14 }: { boatAt?: number; sunAt?: number }) {
  const back = useRef<HTMLCanvasElement>(null);
  const front = useRef<HTMLCanvasElement>(null);
  const boat = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const bc = back.current;
    const fc = front.current;
    const bctx = bc?.getContext("2d");
    const fctx = fc?.getContext("2d");
    if (!bc || !fc || !bctx || !fctx) return;
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let width = 0;
    let frame = 0;

    const resize = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      width = bc.clientWidth;
      for (const [c, ctx] of [[bc, bctx], [fc, fctx]] as const) {
        c.width = width * dpr;
        c.height = HEIGHT * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
    };

    const draw = (ms: number) => {
      const t = ms / 1000;
      bctx.clearRect(0, 0, width, HEIGHT);
      fctx.clearRect(0, 0, width, HEIGHT);
      BACK.forEach((layer, i) => drawLayer(bctx, layer, sample(layer, width, t), i * 1000));
      const pts = sample(FRONT, width, t);
      drawLayer(fctx, FRONT, pts, 9000);

      // Sun glints: a flickering path of sparkles on the water under the sun
      const sunX = width * sunAt;
      for (let i = 0; i < 70; i++) {
        const spread = (hash(i) - 0.5) * 2;
        const x = sunX + spread * Math.abs(spread) * width * 0.22;
        const y = 40 + hash(i + 50) * (HEIGHT - 44);
        const flicker = Math.sin(t * (2 + hash(i + 99) * 4) + i) * 0.5 + 0.5;
        if (flicker < 0.55) continue;
        fctx.fillStyle = `rgba(255,250,225,${(flicker - 0.55) * 1.6 * (1 - Math.abs(spread) * 0.7)})`;
        fctx.fillRect(x, y, 2 + hash(i + 7) * 5, 1);
      }

      // The boat floats on the front surface under it, pitched gently with the slope
      if (boat.current) {
        const bx = width * boatAt;
        const { y, slope } = surfaceAt(pts, bx);
        const roll = Math.atan(slope) * (180 / Math.PI) * 0.6;
        boat.current.style.transform = `translate(${bx}px, ${y}px) translate(-50%, -${(1 - BOAT_WATERLINE) * 100}%) rotate(${roll}deg)`;
      }

      if (!still) frame = requestAnimationFrame(draw);
    };

    resize();
    addEventListener("resize", resize);
    frame = requestAnimationFrame(draw);
    return () => {
      removeEventListener("resize", resize);
      cancelAnimationFrame(frame);
    };
  }, [boatAt, sunAt]);

  return (
    <div className="relative -mt-20" style={{ height: HEIGHT }}>
      <canvas ref={back} className="absolute inset-0 h-full w-full" />
      <div
        ref={boat}
        className="absolute left-0 top-0 will-change-transform"
        style={{ transformOrigin: `50% ${(1 - BOAT_WATERLINE) * 100}%` }}
      >
        <Sailboat />
      </div>
      <canvas ref={front} className="absolute inset-0 h-full w-full" />
    </div>
  );
}

/** A pixel sloop: white sails, a navy hull, and a UofT-blue pennant. */
function Sailboat() {
  return (
    // A 1px slate outline keeps the white sails readable against the hazy horizon.
    <svg
      viewBox="0 0 28 30"
      className="block w-32 [filter:drop-shadow(1px_0_0_#4a6380)_drop-shadow(-1px_0_0_#4a6380)_drop-shadow(0_-1px_0_#4a6380)] sm:w-40"
      shapeRendering="crispEdges"
      aria-hidden
    >
      {/* mast and pennant */}
      <path d="M13 1h1v22h-1z" fill="#2b2b3a" />
      <path d="M14 1h4v1h-1v1h-3z" fill="#3fb4d8" />
      {/* mainsail */}
      <path d="M12 3h1v19h-10v-1h1v-2h1v-2h1v-2h1v-2h1v-2h1v-2h1v-2h1v-2h1v-2h1z" fill="#f4f1ea" />
      <path d="M4 20h8v2h-9v-1h1z" fill="#d9d3c6" />
      {/* jib */}
      <path d="M14 5h1v1h1v2h1v2h1v2h1v2h1v2h1v2h1v2h1v1h-9z" fill="#ffffff" />
      <path d="M14 19h9v2h-9z" fill="#e4e0d6" />
      {/* hull */}
      <path d="M1 23h26v1h-1v1h-1v1h-1v1h-19v-1h-1v-1h-1v-1h-1z" fill="#1e3765" />
      <path d="M1 23h26v1h-26z" fill="#f4f1ea" />
      <path d="M7 25h2v1h-2zM12 25h2v1h-2zM17 25h2v1h-2z" fill="#e8b84a" />
    </svg>
  );
}
