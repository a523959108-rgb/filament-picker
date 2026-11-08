import { describe, expect, it } from "vitest";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import {
  hexDelta,
  hexDeltaOklab,
  isApproxSource,
  isSimilarComparable,
  similar,
  similarLegacy,
  sourceBadge,
} from "../color";
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

  it("calculates OKLab distance and ranks identical colors at zero", () => {
    expect(hexDeltaOklab("#00AE42", "#00AE42")).toBe(0);
    expect(hexDeltaOklab("#000000", "#272729")).toBeGreaterThan(0);
  });

  it("finds similar single-color entries", () => {
    expect(similar(bambu, entries)).toHaveLength(1);
    expect(similar(bambu, entries)[0]?.entry.id).toBe("esun/petg-basic/black");
    expect(similar(cailab, entries)).toEqual([]);
  });

  it("marks store_swatch / image_extracted as approx", () => {
    expect(isApproxSource("official")).toBe(false);
    expect(isApproxSource("ofd")).toBe(false);
    expect(isApproxSource("store_swatch")).toBe(true);
    expect(isApproxSource("image_extracted")).toBe(true);
    expect(similar(bambu, entries)[0]?.isApprox).toBe(true);
  });

  it("excludes translucent / gradient / glow finishes from similar matching", () => {
    const base = { ...bambu, id: "base/red", hex: ["#C8102E"], eff: [] as string[] };
    const silk = { ...bambu, id: "brand/silk-red", hex: ["#C8102E"], eff: ["silk"] };
    const translucent = {
      ...bambu,
      id: "brand/clear-red",
      hex: ["#C8102E"],
      eff: ["translucent"],
    };
    const gradient = {
      ...bambu,
      id: "brand/grad-red",
      hex: ["#C8102E"],
      eff: ["gradient", "multi"],
    };
    expect(isSimilarComparable(translucent)).toBe(false);
    expect(isSimilarComparable(gradient)).toBe(false);
    expect(similar(base, [base, silk, translucent, gradient]).map((m) => m.entry.id)).toEqual([
      "brand/silk-red",
    ]);
    expect(similar(translucent, [base, silk, translucent])).toEqual([]);
  });

  it("prefers same finish for silk over a plain color at equal hex", () => {
    const silkTarget = { ...bambu, id: "a/silk", hex: ["#FF6688"], eff: ["silk"] };
    const plain = { ...bambu, id: "b/plain", hex: ["#FF6688"], eff: [] as string[] };
    const silkPeer = { ...bambu, id: "c/silk", hex: ["#FF6688"], eff: ["silk"] };
    const result = similar(silkTarget, [silkTarget, plain, silkPeer]);
    expect(result.map((m) => m.entry.id)).toEqual(["c/silk", "b/plain"]);
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

  it("improves over legacy by dropping translucent false friends", () => {
    const target = { ...bambu, id: "t/black", hex: ["#101010"], eff: [] as string[] };
    const solid = { ...bambu, id: "t/solid", hex: ["#121212"], eff: [] as string[] };
    const clear = {
      ...bambu,
      id: "t/clear",
      hex: ["#111111"],
      eff: ["translucent"],
    };
    const legacyIds = similarLegacy(target, [target, solid, clear]).map((m) => m.entry.id);
    const nextIds = similar(target, [target, solid, clear]).map((m) => m.entry.id);
    expect(legacyIds).toContain("t/clear");
    expect(nextIds).toEqual(["t/solid"]);
  });

  it("formats source badges", () => {
    expect(sourceBadge("official", 1)).toBe("官方色值");
    expect(sourceBadge("store_swatch", 0.8)).toBe("店铺示意色（近似）");
    expect(sourceBadge("image_extracted", 0.5)).toBe("商品图取色（近似，置信度 0.50）");
    expect(sourceBadge("manual", 0.9)).toBe("人工校对");
    expect(sourceBadge("ofd", 1)).toBe("OFD 官方色");
    expect(sourceBadge(null, null)).toBe("无色值");
  });
});
