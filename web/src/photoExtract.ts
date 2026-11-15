/** Client-side dominant-color extraction. Photos never leave the browser. */

export type Rgb = { r: number; g: number; b: number };

export type DominantColor = { hex: string; share: number };

export const PHOTO_MAX_BYTES = 10 * 1024 * 1024;
export const PHOTO_SAMPLE_LONG_SIDE = 480;
export const PHOTO_CLUSTER_LONG_SIDE = 80;
export const PHOTO_DEFAULT_K = 5;

const ACCEPTED_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
  "image/heic-sequence",
  "image/heif-sequence",
]);

const ACCEPTED_EXT = /\.(jpe?g|png|webp|heic|heif)$/i;

export function photoFileIssue(file: { name: string; type: string; size: number }): string | null {
  if (file.size > PHOTO_MAX_BYTES) {
    return "图片超过 10MB，请压缩后再试。照片只在浏览器里处理，不会上传。";
  }
  const type = file.type.trim().toLowerCase();
  if (ACCEPTED_TYPES.has(type) || ACCEPTED_EXT.test(file.name)) return null;
  return "请上传 JPG、PNG、WebP 或 HEIC。";
}

export function isHeicName(file: { name: string; type: string }): boolean {
  const type = file.type.toLowerCase();
  return type.includes("heic") || type.includes("heif") || /\.hei[cf]$/i.test(file.name);
}

export function rgbToHex(rgb: Rgb): string {
  const channel = (value: number) =>
    Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  return `#${channel(rgb.r)}${channel(rgb.g)}${channel(rgb.b)}`.toUpperCase();
}

/** Mulberry32. Seeded so the same photo extracts the same palette. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function dist2(a: Rgb, b: Rgb): number {
  const dr = a.r - b.r;
  const dg = a.g - b.g;
  const db = a.b - b.b;
  return dr * dr + dg * dg + db * db;
}

function colorKey(rgb: Rgb): number {
  return (Math.round(rgb.r) << 16) | (Math.round(rgb.g) << 8) | Math.round(rgb.b);
}

export type RgbaRaster = {
  data: Uint8ClampedArray;
  width: number;
  height: number;
};

export function rgbAt(raster: RgbaRaster, x: number, y: number): Rgb | null {
  if (x < 0 || y < 0 || x >= raster.width || y >= raster.height) return null;
  const index = (y * raster.width + x) * 4;
  const r = raster.data[index];
  const g = raster.data[index + 1];
  const b = raster.data[index + 2];
  if (r === undefined || g === undefined || b === undefined) return null;
  return { r, g, b };
}

export function downsampleNearest(
  pixels: readonly Rgb[],
  width: number,
  height: number,
  maxSide: number,
): { pixels: Rgb[]; width: number; height: number } {
  if (width < 1 || height < 1 || pixels.length !== width * height) {
    return { pixels: pixels.map((pixel) => ({ ...pixel })), width, height };
  }
  const scale = Math.min(1, maxSide / Math.max(width, height));
  if (scale === 1) {
    return { pixels: pixels.map((pixel) => ({ ...pixel })), width, height };
  }
  const nextWidth = Math.max(1, Math.round(width * scale));
  const nextHeight = Math.max(1, Math.round(height * scale));
  const out: Rgb[] = [];
  for (let y = 0; y < nextHeight; y += 1) {
    const sy = Math.min(height - 1, Math.floor(((y + 0.5) * height) / nextHeight));
    for (let x = 0; x < nextWidth; x += 1) {
      const sx = Math.min(width - 1, Math.floor(((x + 0.5) * width) / nextWidth));
      const pixel = pixels[sy * width + sx];
      if (pixel !== undefined) out.push({ ...pixel });
    }
  }
  return { pixels: out, width: nextWidth, height: nextHeight };
}

export function downsampleRaster(
  raster: RgbaRaster,
  maxSide: number,
): { pixels: Rgb[]; width: number; height: number } {
  const scale = Math.min(1, maxSide / Math.max(raster.width, raster.height));
  const width = Math.max(1, Math.round(raster.width * scale));
  const height = Math.max(1, Math.round(raster.height * scale));
  const pixels: Rgb[] = [];
  for (let y = 0; y < height; y += 1) {
    const sy = Math.min(raster.height - 1, Math.floor(((y + 0.5) * raster.height) / height));
    for (let x = 0; x < width; x += 1) {
      const sx = Math.min(raster.width - 1, Math.floor(((x + 0.5) * raster.width) / width));
      const rgb = rgbAt(raster, sx, sy);
      if (rgb !== null) pixels.push(rgb);
    }
  }
  return { pixels, width, height };
}

/**
 * Drop a flat border (typical photo backdrop). If the border is busy, or stripping
 * it would erase the picture, keep every pixel.
 */
export function foregroundPixels(
  pixels: readonly Rgb[],
  width: number,
  height: number,
): Rgb[] {
  if (width < 3 || height < 3 || pixels.length !== width * height) {
    return pixels.map((pixel) => ({ ...pixel }));
  }
  const borderPx = Math.max(1, Math.round(Math.min(width, height) * 0.06));
  const border: Rgb[] = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (x < borderPx || y < borderPx || x >= width - borderPx || y >= height - borderPx) {
        const pixel = pixels[y * width + x];
        if (pixel !== undefined) border.push(pixel);
      }
    }
  }
  if (border.length === 0) return pixels.map((pixel) => ({ ...pixel }));
  const mean = {
    r: border.reduce((sum, pixel) => sum + pixel.r, 0) / border.length,
    g: border.reduce((sum, pixel) => sum + pixel.g, 0) / border.length,
    b: border.reduce((sum, pixel) => sum + pixel.b, 0) / border.length,
  };
  const rms = Math.sqrt(border.reduce((sum, pixel) => sum + dist2(pixel, mean), 0) / border.length);
  if (rms > 18) return pixels.map((pixel) => ({ ...pixel }));
  const kept = pixels.filter((pixel) => dist2(pixel, mean) > 26 * 26);
  if (kept.length < Math.max(8, pixels.length * 0.05)) {
    return pixels.map((pixel) => ({ ...pixel }));
  }
  return kept;
}

export function kmeansRgb(
  pixels: readonly Rgb[],
  k: number,
  seed = 0,
): { center: Rgb; share: number }[] {
  if (pixels.length === 0 || k < 1) return [];
  const unique = new Set(pixels.map(colorKey));
  const count = Math.min(k, unique.size, pixels.length);
  const random = mulberry32(seed);
  const centers: Rgb[] = [];
  const first = Math.min(pixels.length - 1, Math.floor(random() * pixels.length));
  const firstPixel = pixels[first];
  if (firstPixel === undefined) return [];
  centers.push({ ...firstPixel });

  while (centers.length < count) {
    const distances = pixels.map((pixel) => {
      let best = Infinity;
      for (const center of centers) best = Math.min(best, dist2(pixel, center));
      return best;
    });
    const total = distances.reduce((sum, value) => sum + value, 0);
    let index = 0;
    if (total <= 0) {
      index = Math.min(pixels.length - 1, Math.floor(random() * pixels.length));
    } else {
      let pick = random() * total;
      for (let i = 0; i < distances.length; i += 1) {
        pick -= distances[i] ?? 0;
        if (pick <= 0) {
          index = i;
          break;
        }
      }
    }
    const chosen = pixels[index] ?? pixels[0];
    if (chosen === undefined) break;
    centers.push({ ...chosen });
  }

  let labels = new Array<number>(pixels.length).fill(0);
  for (let iter = 0; iter < 20; iter += 1) {
    for (let i = 0; i < pixels.length; i += 1) {
      const pixel = pixels[i];
      if (pixel === undefined) continue;
      let best = 0;
      let bestDistance = Infinity;
      for (let c = 0; c < centers.length; c += 1) {
        const center = centers[c];
        if (center === undefined) continue;
        const distance = dist2(pixel, center);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = c;
        }
      }
      labels[i] = best;
    }
    let shift = 0;
    for (let c = 0; c < centers.length; c += 1) {
      let r = 0;
      let g = 0;
      let b = 0;
      let n = 0;
      for (let i = 0; i < pixels.length; i += 1) {
        if (labels[i] !== c) continue;
        const pixel = pixels[i];
        if (pixel === undefined) continue;
        r += pixel.r;
        g += pixel.g;
        b += pixel.b;
        n += 1;
      }
      if (n === 0) continue;
      const next = { r: r / n, g: g / n, b: b / n };
      const prev = centers[c];
      if (prev === undefined) continue;
      shift = Math.max(
        shift,
        Math.abs(next.r - prev.r),
        Math.abs(next.g - prev.g),
        Math.abs(next.b - prev.b),
      );
      centers[c] = next;
    }
    if (shift < 0.01) break;
  }

  const counts = new Array<number>(centers.length).fill(0);
  labels = new Array<number>(pixels.length).fill(0);
  for (let i = 0; i < pixels.length; i += 1) {
    const pixel = pixels[i];
    if (pixel === undefined) continue;
    let best = 0;
    let bestDistance = Infinity;
    for (let c = 0; c < centers.length; c += 1) {
      const center = centers[c];
      if (center === undefined) continue;
      const distance = dist2(pixel, center);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = c;
      }
    }
    labels[i] = best;
    counts[best] = (counts[best] ?? 0) + 1;
  }

  return centers
    .map((center, index) => ({ center, share: (counts[index] ?? 0) / pixels.length }))
    .filter((cluster) => cluster.share > 0)
    .sort((a, b) => b.share - a.share || a.center.r - b.center.r);
}

export function extractDominantColors(
  pixels: readonly Rgb[],
  width: number,
  height: number,
  options?: { k?: number; seed?: number; maxColors?: number },
): DominantColor[] {
  const down = downsampleNearest(pixels, width, height, PHOTO_CLUSTER_LONG_SIDE);
  const foreground = foregroundPixels(down.pixels, down.width, down.height);
  const k = options?.k ?? PHOTO_DEFAULT_K;
  const clusters = kmeansRgb(foreground, k, options?.seed ?? 0);
  const kept = clusters.filter((cluster) => cluster.share >= 0.04);
  const used = kept.length > 0 ? kept : clusters.slice(0, 1);
  const merged = new Map<string, number>();
  for (const cluster of used) {
    const hex = rgbToHex(cluster.center);
    merged.set(hex, (merged.get(hex) ?? 0) + cluster.share);
  }
  return [...merged.entries()]
    .map(([hex, share]) => ({ hex, share }))
    .sort((a, b) => b.share - a.share || a.hex.localeCompare(b.hex))
    .slice(0, options?.maxColors ?? k);
}

export function drawSample(
  image: CanvasImageSource,
  sourceWidth: number,
  sourceHeight: number,
  maxSide: number,
): RgbaRaster | null {
  if (!(sourceWidth > 0) || !(sourceHeight > 0)) return null;
  const scale = Math.min(1, maxSide / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (context === null) return null;
  context.drawImage(image, 0, 0, width, height);
  const imageData = context.getImageData(0, 0, width, height);
  return { data: new Uint8ClampedArray(imageData.data), width, height };
}
