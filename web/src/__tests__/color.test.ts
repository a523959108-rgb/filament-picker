import { describe, expect, it } from "vitest";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { hexDelta, similar, sourceBadge } from "../color";
import type { WebEntry } from "../types";

const entries = sample.entries as WebEntry[];
const bambu = entries[0];
const cailab = entries[2];

describe("color helpers", () => {
  it("calculates CIEDE2000 deltas", () => {
    expect(hexDelta("#000000", "#272729")).toBeGreaterThan(9.6);
    expect(hexDelta("#000000", "#272729")).toBeLessThan(9.9);
    expect(hexDelta("#00AE42", "#00AE42")).toBe(0);
  });

  it("finds similar single-color entries", () => {
    expect(similar(bambu, entries)).toHaveLength(1);
    expect(similar(bambu, entries)[0]?.entry.id).toBe("esun/petg-basic/black");
    expect(similar(cailab, entries)).toEqual([]);
  });

  it("limits and sorts similar entries while excluding multi-color entries", () => {
    const grayEntries = Array.from({ length: 12 }, (_, index) => ({
      ...bambu,
      id: `gray/${index}`,
      hex: [`#${(index * 12).toString(16).padStart(2, "0").repeat(3)}`],
      eff: index === 11 ? ["multi"] : [],
    }));
    const result = similar(grayEntries[0], grayEntries);
    expect(result.length).toBeLessThanOrEqual(8);
    expect(result.map((item) => item.delta)).toEqual(
      [...result.map((item) => item.delta)].sort((a, b) => a - b),
    );
    expect(result.some((item) => item.entry.eff.includes("multi"))).toBe(false);
  });

  it("formats source badges", () => {
    expect(sourceBadge("official", 1)).toBe("官方色值");
    expect(sourceBadge("store_swatch", 0.8)).toBe("店铺示意色（近似）");
    expect(sourceBadge("image_extracted", 0.5)).toBe("商品图取色（近似，置信度 0.50）");
    expect(sourceBadge("manual", 0.9)).toBe("人工校对");
    expect(sourceBadge(null, null)).toBe("无色值");
  });
});
