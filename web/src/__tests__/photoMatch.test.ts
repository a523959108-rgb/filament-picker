import { describe, expect, it } from "vitest";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { hexDelta } from "../color";
import {
  PHOTO_CLOSE_DE,
  RYBW_STACK_BASES,
  nearestSkus,
  singleIsClose,
  suggestStack,
} from "../photoMatch";
import { colorsFromHash, modeFromHash, stackHrefForColors } from "../stackPrefill";
import type { WebCatalog, WebEntry } from "../types";

const catalog = sample as WebCatalog;
const bambu = catalog.entries[0] as WebEntry;

describe("nearest filament SKUs", () => {
  it("ranks an exact black ahead of the nearby store swatch and keeps the shop link", () => {
    const matches = nearestSkus("#000000", catalog.entries, catalog.brands, 4);
    expect(matches.map((match) => match.entry.id)).toEqual([
      "bambu-lab/petg-basic/black-30105",
      "esun/petg-basic/black",
    ]);
    expect(matches[0]?.delta).toBe(0);
    expect(matches[0]?.label).toBe("几乎一样");
    expect(matches[0]?.brandName).toBe("Bambu Lab");
    expect(matches[0]?.name).toBe("黑色 Black（30105）");
    expect(matches[0]?.price).toBe("¥2,800 JPY");
    expect(matches[0]?.purchaseUrl).toContain("pinduoduo.com");
    expect(matches[1]?.isApprox).toBe(true);
    expect(singleIsClose(matches)).toBe(true);
  });

  it("skips gradient and colorless entries, and prefers a purchasable tie", () => {
    const shop = {
      ...bambu,
      id: "b/shop",
      hex: ["#123456"],
      url: "https://shop.example/spool",
      alt_url: null,
      price: "¥40 CNY",
      eff: [] as string[],
    };
    const unlink = {
      ...bambu,
      id: "a/no-link",
      hex: ["#123456"],
      url: "",
      alt_url: null,
      price: null,
      eff: [] as string[],
    };
    const silk = { ...shop, id: "c/silk", eff: ["silk"] };
    const clear = { ...shop, id: "d/clear", hex: ["#123456"], eff: ["translucent"] };
    const matches = nearestSkus("#123456", [unlink, clear, silk, shop, catalog.entries[2] as WebEntry], catalog.brands);
    expect(matches.map((match) => match.entry.id)).toEqual(["b/shop", "c/silk", "a/no-link"]);
    expect(matches[0]?.purchaseUrl).toBe("https://shop.example/spool");
    expect(matches.some((match) => match.entry.id === "d/clear")).toBe(false);
  });

  it("marks a color far from every swatch as not close enough", () => {
    const matches = nearestSkus("#00FF00", catalog.entries, catalog.brands);
    expect(matches[0]?.label).toBe("偏远");
    expect(matches[0]?.delta).toBeGreaterThan(PHOTO_CLOSE_DE);
    expect(singleIsClose(matches)).toBe(false);
  });
});

describe("RYBW stacking suggestion", () => {
  it("uses the tray-map bases and reproduces a tray color with one spool", () => {
    expect(RYBW_STACK_BASES.map((base) => base.slot)).toEqual(["R", "Y", "B", "W"]);
    const red = RYBW_STACK_BASES.find((base) => base.slot === "R");
    expect(red?.catalog_id).toBe("bambu-lab/pla-matte/scarlet-red-11200");
    const suggestion = suggestStack(red?.hex ?? "#DE4343");
    expect(suggestion).not.toBeNull();
    expect(suggestion?.mode).toBe("RYBW");
    expect(suggestion?.delta).toBeLessThan(0.05);
    expect(suggestion?.parts).toEqual([
      expect.objectContaining({ slot: "R", weight: 1 }),
    ]);
  });

  it("mixes red and yellow for orange and beats the nearest single tray color", () => {
    const suggestion = suggestStack("#FF8800");
    expect(suggestion).not.toBeNull();
    if (suggestion === null) return;
    const weight = suggestion.parts.reduce((sum, part) => sum + part.weight, 0);
    expect(weight).toBeCloseTo(1, 5);
    expect(suggestion.parts.map((part) => part.slot).sort()).toEqual(["R", "Y"]);
    const nearestBase = Math.min(...RYBW_STACK_BASES.map((base) => hexDelta("#FF8800", base.hex)));
    expect(suggestion.delta).toBeLessThan(nearestBase);
    expect(suggestion.delta).toBeLessThan(hexDelta("#FF8800", "#000000"));
  });
});

describe("stack color prefill", () => {
  it("reads colors and mode, and points the main site at the stack subdomain", () => {
    expect(colorsFromHash("#/stack?colors=de4343,zz,00ae42,DE4343&mode=rybw")).toEqual([
      "#DE4343",
      "#00AE42",
    ]);
    expect(modeFromHash("#/stack?colors=DE4343&mode=cmyw")).toBe("CMYW");
    expect(modeFromHash("#/stack")).toBeNull();
    expect(stackHrefForColors("localhost", ["#de4343", "00AE42"])).toBe(
      "#/stack?colors=DE4343,00AE42&mode=RYBW",
    );
    expect(stackHrefForColors("filament.ibaozi.com", ["#112233"])).toBe(
      "https://stack.filament.ibaozi.com/#/stack?colors=112233&mode=RYBW",
    );
  });
});
