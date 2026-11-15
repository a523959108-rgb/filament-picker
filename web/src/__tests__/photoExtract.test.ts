import { describe, expect, it } from "vitest";
import {
  downsampleNearest,
  extractDominantColors,
  kmeansRgb,
  photoFileIssue,
  rgbAt,
  rgbToHex,
  PHOTO_MAX_BYTES,
  type Rgb,
} from "../photoExtract";

function fill(width: number, height: number, paint: (x: number, y: number) => Rgb): Rgb[] {
  const pixels: Rgb[] = [];
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) pixels.push(paint(x, y));
  }
  return pixels;
}

describe("photo color extraction", () => {
  it("formats rounded hex and reads a pixel", () => {
    expect(rgbToHex({ r: 255, g: 0.2, b: 16 })).toBe("#FF0010");
    const raster = {
      data: new Uint8ClampedArray([1, 2, 3, 255, 9, 8, 7, 255]),
      width: 2,
      height: 1,
    };
    expect(rgbAt(raster, 1, 0)).toEqual({ r: 9, g: 8, b: 7 });
    expect(rgbAt(raster, 2, 0)).toBeNull();
  });

  it("rejects oversized and unknown files, and accepts heic by extension", () => {
    expect(photoFileIssue({ name: "a.jpg", type: "image/jpeg", size: 100 })).toBeNull();
    expect(photoFileIssue({ name: "a.HEIC", type: "", size: 100 })).toBeNull();
    expect(photoFileIssue({ name: "a.txt", type: "text/plain", size: 4 })).toMatch(/JPG/);
    expect(photoFileIssue({ name: "big.png", type: "image/png", size: PHOTO_MAX_BYTES + 1 })).toMatch(/10MB/);
  });

  it("downsamples with nearest neighbor", () => {
    const pixels = fill(4, 2, (x) => (x < 2 ? { r: 255, g: 0, b: 0 } : { r: 0, g: 0, b: 255 }));
    const down = downsampleNearest(pixels, 4, 2, 2);
    expect(down.width).toBe(2);
    expect(down.height).toBe(1);
    expect(down.pixels.map(rgbToHex)).toEqual(["#FF0000", "#0000FF"]);
  });

  it("splits a red/blue field into two equal clusters", () => {
    const pixels = fill(8, 8, (x) => (x < 4 ? { r: 255, g: 0, b: 0 } : { r: 0, g: 0, b: 255 }));
    const clusters = kmeansRgb(pixels, 2, 0);
    expect(clusters).toHaveLength(2);
    expect(clusters.map((cluster) => rgbToHex(cluster.center)).sort()).toEqual(["#0000FF", "#FF0000"]);
    expect(clusters[0]?.share).toBeCloseTo(0.5, 5);
    expect(clusters[1]?.share).toBeCloseTo(0.5, 5);
  });

  it("ignores a flat white border and keeps the red object", () => {
    const pixels = fill(12, 12, (x, y) =>
      x > 0 && y > 0 && x < 11 && y < 11 ? { r: 200, g: 30, b: 40 } : { r: 250, g: 250, b: 250 },
    );
    const colors = extractDominantColors(pixels, 12, 12, { k: 3, seed: 0 });
    expect(colors[0]?.hex).toBe("#C81E28");
    expect(colors[0]?.share).toBeGreaterThan(0.8);
    expect(colors.some((color) => color.hex === "#FAFAFA")).toBe(false);
  });

  it("is stable for the same seed", () => {
    const pixels = fill(10, 10, (x, y) => ({
      r: (x * 40 + y * 3) % 256,
      g: (y * 25) % 256,
      b: (x * 10) % 256,
    }));
    const once = extractDominantColors(pixels, 10, 10, { k: 4, seed: 0 });
    const twice = extractDominantColors(pixels, 10, 10, { k: 4, seed: 0 });
    expect(twice).toEqual(once);
    expect(once.length).toBeGreaterThan(0);
    expect(once.length).toBeLessThanOrEqual(4);
  });
});
