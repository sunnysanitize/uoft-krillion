"use client";

import { useEffect, useRef } from "react";

type Puff = [cx: number, cy: number, r: number];
type Shape = { w: number; h: number; base: number; puffs: Puff[] };

/**
 * Hand-balanced cumulus on small pixel grids: the biggest puff a little off-centre, smaller ones
 * tapering out to each side, all cut off flat at `base`.
 */
export const CLOUD_SHAPES: Shape[] = [
  // a big full cumulus
  { w: 64, h: 28, base: 26, puffs: [[13, 21, 7], [25, 15, 11], [39, 16, 10], [51, 21, 7], [32, 22, 8]] },
  // a medium one
  { w: 48, h: 22, base: 20, puffs: [[10, 16, 6], [20, 11, 8], [31, 13, 7], [40, 17, 5]] },
  // a long, low fair-weather cloud
  { w: 76, h: 20, base: 18, puffs: [[9, 14, 5], [19, 11, 7], [31, 9, 8], [44, 11, 7], [56, 13, 6], [66, 15, 4]] },
  // a little puff
  { w: 32, h: 16, base: 14, puffs: [[8, 11, 5], [16, 8, 6], [24, 11, 5]] },
];

// Three tones plus a cool base: white caps, soft white body, pale blue shade low down.
const CAP = [255, 255, 255];
const BODY = [244, 248, 252];
const SHADE = [222, 234, 245];
const BASE = [200, 218, 234];

function inside([cx, cy, r]: Puff, x: number, y: number) {
  return (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r;
}

/** One cloud, drawn once at grid size and scaled up as crisp square pixels. */
export function Cloud({ shape, left, top, pixel = 5 }: { shape: number; left: number; top: number; pixel?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const s = CLOUD_SHAPES[shape];

  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const { w, h, base, puffs } = CLOUD_SHAPES[shape];
    const img = ctx.createImageData(w, h);
    for (let y = 0; y <= base; y++) {
      for (let x = 0; x < w; x++) {
        const over = puffs.filter((p) => inside(p, x, y));
        if (!over.length) continue;
        // The cap of whichever puff is highest here catches the light.
        const highest = over.reduce((a, b) => (a[1] - a[2] < b[1] - b[2] ? a : b));
        const rgb =
          base - y < 2 ? BASE
          : y > base - 5 ? SHADE
          : y < highest[1] - highest[2] * 0.45 ? CAP
          : BODY;
        img.data.set([...rgb, 255], (y * w + x) * 4);
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [shape]);

  return (
    <canvas
      ref={ref}
      width={s.w}
      height={s.h}
      className="absolute"
      style={{ left: `${left}%`, top: `${top}%`, width: s.w * pixel, height: s.h * pixel, imageRendering: "pixelated" }}
      aria-hidden
    />
  );
}
