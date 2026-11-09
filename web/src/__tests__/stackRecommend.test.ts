import { describe, expect, it } from "vitest";
import catalog from "../../public/web-catalog.json";
import { isPddGoodsUrl } from "../marketPrice";
import {
  PREFERRED_DELTA_THRESHOLD,
  SMOKE_RYBW_SLOTS,
  pickPurchaseUrl,
  recommendForHex,
  recommendForHexCascaded,
  recommendSlots,
  toStackResult,
} from "../stackRecommend";
import type { WebCatalog } from "../types";

const entries = (catalog as WebCatalog).entries;

describe("stackRecommend", () => {
  it("cascades red slot off Basic when ΔE exceeds threshold", () => {
    const recs = recommendSlots(SMOKE_RYBW_SLOTS, entries, {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
    expect(recs).toHaveLength(4);
    const bySlot = Object.fromEntries(recs.map((rec) => [rec.slot, rec]));

    expect(bySlot.W?.entry.id).toBe("bambu-lab/pla-basic/light-gray-10104");
    expect(bySlot.W?.match_tier).toBe("preferred_series");

    expect(bySlot.Y?.entry.id).toBe("bambu-lab/pla-basic/yellow-10400");
    expect(bySlot.B?.entry.id).toBe("bambu-lab/pla-basic/cobalt-blue-10604");

    // Red: Basic #C12E1F is ΔE~11.26 > 8 → Matte scarlet
    expect(bySlot.R?.entry.id).toBe("bambu-lab/pla-matte/scarlet-red-11200");
    expect(bySlot.R?.match_tier).toBe("same_brand_fallback");
    expect(bySlot.R?.delta_e).toBeLessThan(PREFERRED_DELTA_THRESHOLD);
    expect(bySlot.R?.purchase_is_pdd).toBe(true);
    expect(bySlot.R?.alternates.some((alt) => alt.entry.id === "bambu-lab/pla-basic/red-10200")).toBe(
      true,
    );

    for (const rec of recs) {
      expect(rec.purchase_url).toBeTruthy();
      expect(rec.match_reason.length).toBeGreaterThan(0);
      expect(rec.delta_e).toBeGreaterThanOrEqual(0);
    }
  });

  it("keeps Basic-only nearest via recommendForHex", () => {
    const match = recommendForHex("#E94A39", entries, {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
    expect(match?.entry.id).toBe("bambu-lab/pla-basic/red-10200");
    expect(match?.delta_e).toBeGreaterThan(PREFERRED_DELTA_THRESHOLD);
  });

  it("explain cascaded red primary vs lut nominal", () => {
    const cascaded = recommendForHexCascaded("#E94A39", entries, {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
    expect(cascaded?.primary.entry.id).toBe("bambu-lab/pla-matte/scarlet-red-11200");
    expect(cascaded?.alternates[0]?.entry.id).toBe("bambu-lab/pla-basic/red-10200");
  });

  it("prefers a PDD goods URL when primary is search-only", () => {
    const entry = {
      id: "x",
      b: "bambu-lab",
      s: "PLA Basic",
      m: "PLA" as const,
      en: "Demo",
      zh: "演示",
      code: null,
      py: null,
      pyi: null,
      fam: "红",
      eff: [] as string[],
      hex: ["#E94A39"],
      src: "official" as const,
      conf: 1,
      url: "https://mobile.pinduoduo.com/search_result.html?search_key=demo",
      alt_url: "https://mobile.pinduoduo.com/goods.html?goods_id=123456789012",
      price: null,
      img: null,
    };
    const picked = pickPurchaseUrl(entry);
    expect(picked.isPdd).toBe(true);
    expect(picked.url).toContain("goods_id=123456789012");
  });

  it("returns null when pool is empty", () => {
    expect(recommendForHex("#FFFFFF", [], { brandSlug: "nope" })).toBeNull();
  });

  it("builds a lumina-stack-result payload with tiers", () => {
    const recs = recommendSlots(SMOKE_RYBW_SLOTS, entries, {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
    const result = toStackResult({
      lutMode: "RYBW",
      slots: recs,
      previewRelpath: "stack-smoke/preview.png",
      model3mfRelpath: "stack-smoke/smoke_rybw_sample_logo.3mf",
      createdAt: "2026-11-09T17:08:00+09:00",
    });
    expect(result.kind).toBe("lumina-stack-result");
    expect(result.slots).toHaveLength(4);
    expect(result.slots.find((s) => s.slot === "R")?.match_tier).toBe("same_brand_fallback");
    expect(result.preview_relpath).toContain("preview.png");
  });
});
