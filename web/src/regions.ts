export interface SampleRegion {
  space: "norm";
  x: number;
  y: number;
  w?: number;
  h?: number;
  r?: number;
}

export const POINT_RADIUS = 0.04;
export const CLICK_SLOP_PX = 4;

export interface NormPoint {
  x: number;
  y: number;
}

export function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000;
}

export function regionFromDrag(
  start: NormPoint,
  end: NormPoint,
  boxWidth: number,
  boxHeight: number,
): SampleRegion {
  const dx = (end.x - start.x) * boxWidth;
  const dy = (end.y - start.y) * boxHeight;
  const x = clamp01(Math.min(start.x, end.x));
  const y = clamp01(Math.min(start.y, end.y));
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  if (Math.hypot(dx, dy) < CLICK_SLOP_PX || w < 0.01 || h < 0.01) {
    return { space: "norm", x: round4(clamp01(end.x)), y: round4(clamp01(end.y)), r: POINT_RADIUS };
  }
  return { space: "norm", x: round4(x), y: round4(y), w: round4(w), h: round4(h) };
}

export function pointInBox(
  clientX: number,
  clientY: number,
  box: { left: number; top: number; width: number; height: number },
): NormPoint {
  const width = box.width || 1;
  const height = box.height || 1;
  return {
    x: clamp01((clientX - box.left) / width),
    y: clamp01((clientY - box.top) / height),
  };
}
