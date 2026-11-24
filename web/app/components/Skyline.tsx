type R = [x: number, y: number, w: number, h: number];

// Hand-placed pixel silhouettes on a 200 x 48 grid, west to east:
// Hart House, Soldiers' Tower, Convocation Hall, Robarts, and the CN Tower on the horizon.
const HORIZON: R[] = [
  [176, 4, 2, 44], [173, 16, 8, 4], [174, 20, 6, 2], [176.5, 0, 1, 4], // CN Tower
  [158, 36, 10, 12], [186, 32, 8, 16], [194, 38, 6, 10], // downtown blocks
];

const CAMPUS: R[] = [
  // Hart House: long gothic block with crenellations
  [6, 34, 42, 14], [6, 31, 3, 3], [12, 31, 3, 3], [18, 31, 3, 3], [24, 31, 3, 3], [30, 31, 3, 3], [36, 31, 3, 3], [42, 31, 3, 3], [45, 31, 3, 3],
  // Soldiers' Tower
  [52, 12, 10, 36], [51, 12, 12, 2], [54, 6, 6, 6], [56, 2, 2, 4],
  // trees
  [64, 40, 8, 8], [66, 37, 4, 3], [100, 41, 7, 7], [102, 38, 3, 3],
  // Convocation Hall: drum + dome
  [74, 38, 26, 10], [76, 34, 22, 4], [79, 31, 16, 3], [82, 29, 10, 2], [86, 26, 2, 3],
  // Robarts: the stepped concrete peacock
  [108, 40, 46, 8], [112, 32, 38, 8], [117, 25, 28, 7], [123, 19, 16, 6], [104, 36, 6, 12], [152, 36, 6, 12],
];

const LIT: R[] = [
  [56, 18, 2, 2], // the clock face
  [14, 38, 1, 2], [27, 38, 1, 2], [40, 38, 1, 2],
  [116, 35, 1, 1], [124, 35, 1, 1], [139, 35, 1, 1], [145, 35, 1, 1], [127, 28, 1, 1], [134, 28, 1, 1], [131, 22, 1, 1],
  [188, 36, 1, 1], [190, 40, 1, 1],
];

const rects = (list: R[], fill: string) =>
  list.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} fill={fill} />);

/** St. George campus at night, sitting on the waterline. */
export function Skyline({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 48"
      className={className}
      shapeRendering="crispEdges"
      role="img"
      aria-label="Pixel skyline of the St. George campus: Hart House, Soldiers' Tower, Convocation Hall and Robarts Library"
    >
      {rects(HORIZON, "#0f2447")}
      {rects(CAMPUS, "#050d1e")}
      {rects(LIT, "var(--color-gold)")}
    </svg>
  );
}
