/** Catalog recommendations for stack slots. No GPL / no opencv. */

import { hexDelta } from "./color";
import { isPddGoodsUrl } from "./marketPrice";
import { purchaseHref } from "./purchase";
import type { StackLutMode } from "./stackJob";
import type { WebEntry } from "./types";

export type SmokeSlotTarget = {
  extruder: number;
  slot: string;
  name_zh: string;
  name_en: string;
  engine_hex: string;
};

/** Lumina bambulab_pla_basic_rybw smoke extruder colours (2026-11-09). */
export const SMOKE_RYBW_SLOTS: SmokeSlotTarget[] = [
  { extruder: 1, slot: "W", name_zh: "白", name_en: "White", engine_hex: "#D7D2CF" },
  { extruder: 2, slot: "R", name_zh: "红", name_en: "Red", engine_hex: "#E94A39" },
  { extruder: 3, slot: "Y", name_zh: "黄", name_en: "Yellow", engine_hex: "#ECEF35" },
  { extruder: 4, slot: "B", name_zh: "蓝", name_en: "Blue", engine_hex: "#3451B1" },
];

export const SMOKE_PREVIEW_URL = "./stack-smoke/preview.png";
export const SMOKE_MODEL_3MF_URL = "./stack-smoke/smoke_rybw_sample_logo.3mf";
export const SMOKE_INPUT_URL = "./stack-smoke/input_sample_logo.png";

/** If preferred-series ΔE exceeds this, promote same-brand / cross-brand fallback. */
export const PREFERRED_DELTA_THRESHOLD = 8;

export type MatchTier = "preferred_series" | "same_brand_fallback" | "cross_brand_fallback";

export type RankedMatch = {
  entry: WebEntry;
  catalog_hex: string;
  delta_e: number;
  purchase_url: string | null;
  purchase_is_pdd: boolean;
  match_tier: MatchTier;
  match_reason: string;
};

export type SlotRecommendation = {
  extruder: number;
  slot: string;
  name_zh: string;
  name_en: string;
  engine_hex: string;
  entry: WebEntry;
  catalog_hex: string;
  delta_e: number;
  purchase_url: string | null;
  purchase_is_pdd: boolean;
  match_tier: MatchTier;
  match_reason: string;
  /** Other honest options (e.g. LUT 名义 Basic when primary fell back). */
  alternates: RankedMatch[];
};

export type StackResultSlot = {
  extruder: number;
  slot: string;
  name_zh: string;
  name_en: string;
  engine_hex: string;
  recommended_id: string;
  recommended_hex: string;
  recommended_name: string;
  delta_e: number;
  purchase_url: string | null;
  purchase_is_pdd: boolean;
  match_tier?: MatchTier;
  match_reason?: string;
  alternates?: {
    recommended_id: string;
    recommended_hex: string;
    recommended_name: string;
    delta_e: number;
    purchase_url: string | null;
    purchase_is_pdd: boolean;
    match_tier: MatchTier;
    match_reason: string;
  }[];
};

export type StackResult = {
  schema_version: 1;
  kind: "lumina-stack-result";
  created_at: string;
  lut_mode: StackLutMode;
  source_job_kind: "lumina-stack-job";
  preview_relpath: string | null;
  model_3mf_relpath: string | null;
  /** Optional embedded preview (data URL or raw base64 PNG/JPEG/WebP). */
  preview_data_url?: string | null;
  preview_base64?: string | null;
  model_3mf_data_url?: string | null;
  model_3mf_base64?: string | null;
  slots: StackResultSlot[];
  note: string;
};

export type RecommendOptions = {
  brandSlug?: string;
  seriesIncludes?: string;
  material?: "PLA" | "PETG";
  /** Prefer-series ΔE above this triggers same-brand / cross-brand promotion. */
  preferredDeltaThreshold?: number;
  /** When true (default), allow same-brand other series if preferred ΔE is high. */
  allowSameBrandFallback?: boolean;
  /** When true (default), attach best cross-brand PLA as an alternate (and promote if still needed). */
  allowCrossBrandFallback?: boolean;
};

function singleHex(entry: WebEntry): string | null {
  if (entry.hex.length !== 1) return null;
  const value = entry.hex[0];
  return value === undefined ? null : value;
}

/** Prefer PDD goods URL on primary or alt; else first purchaseHref-able URL. */
export function pickPurchaseUrl(entry: WebEntry): { url: string | null; isPdd: boolean } {
  const candidates = [entry.url, entry.alt_url ?? ""].map((value) => value.trim()).filter(Boolean);
  for (const candidate of candidates) {
    if (isPddGoodsUrl(candidate)) {
      return { url: candidate, isPdd: true };
    }
  }
  for (const candidate of candidates) {
    const href = purchaseHref(candidate);
    if (href !== null) {
      return { url: href, isPdd: false };
    }
  }
  return { url: null, isPdd: false };
}

function inPool(
  entry: WebEntry,
  options: {
    brandSlug?: string;
    seriesIncludes?: string;
    material?: "PLA" | "PETG";
  },
): boolean {
  if (singleHex(entry) === null) return false;
  if (entry.eff.includes("multi")) return false;
  // Translucent / silk finishes are poor stack-base substitutes.
  if (entry.eff.some((effect) => effect.includes("translucent") || effect.includes("transparent") || effect.includes("silk"))) {
    return false;
  }
  const series = (entry.s ?? "").toLowerCase();
  if (series.includes("translucent") || series.includes("silk")) return false;
  if (options.brandSlug !== undefined && entry.b !== options.brandSlug) return false;
  if (options.seriesIncludes !== undefined && !(entry.s ?? "").includes(options.seriesIncludes)) {
    return false;
  }
  if (options.material !== undefined && entry.m !== options.material) return false;
  return true;
}

function rankPool(
  engineHex: string,
  pool: WebEntry[],
  matchTier: MatchTier,
  reasonFor: (entry: WebEntry, delta: number) => string,
): RankedMatch[] {
  /** Soft PDD pull for fallback tiers so purchasable near-matches beat orphan search links. */
  const pddBonus = matchTier === "preferred_series" ? 0 : 1.0;
  const ranked = pool.map((entry) => {
    const catalogHex = singleHex(entry) as string;
    const delta = hexDelta(engineHex, catalogHex);
    const purchase = pickPurchaseUrl(entry);
    const match: RankedMatch = {
      entry,
      catalog_hex: catalogHex,
      delta_e: delta,
      purchase_url: purchase.url,
      purchase_is_pdd: purchase.isPdd,
      match_tier: matchTier,
      match_reason: reasonFor(entry, delta),
    };
    const sortKey = delta - (purchase.isPdd ? pddBonus : 0);
    return { match, sortKey };
  });
  ranked.sort(
    (a, b) =>
      a.sortKey - b.sortKey ||
      a.match.delta_e - b.match.delta_e ||
      Number(b.match.purchase_is_pdd) - Number(a.match.purchase_is_pdd) ||
      a.match.entry.id.localeCompare(b.match.entry.id),
  );
  return ranked.map((row) => row.match);
}

/**
 * Nearest catalog colour for one engine slot hex (single pool).
 * Ranking: CIEDE2000, then prefer PDD goods, then id.
 */
export function recommendForHex(
  engineHex: string,
  entries: WebEntry[],
  options: RecommendOptions = {},
): { entry: WebEntry; catalog_hex: string; delta_e: number } | null {
  const pool = entries.filter((entry) =>
    inPool(entry, {
      brandSlug: options.brandSlug,
      seriesIncludes: options.seriesIncludes,
      material: options.material,
    }),
  );
  const ranked = rankPool(engineHex, pool, "preferred_series", () => "pool nearest");
  const best = ranked[0];
  if (best === undefined) return null;
  return { entry: best.entry, catalog_hex: best.catalog_hex, delta_e: best.delta_e };
}

function displayName(entry: WebEntry): string {
  return entry.zh || entry.en || entry.id;
}

/**
 * Cascading recommend: preferred series → same-brand other series → cross-brand.
 * Promotes fallback when preferred ΔE exceeds threshold so red-like slots are honest.
 */
export function recommendForHexCascaded(
  engineHex: string,
  entries: WebEntry[],
  options: RecommendOptions = {},
): { primary: RankedMatch; alternates: RankedMatch[] } | null {
  const brandSlug = options.brandSlug ?? "bambu-lab";
  const seriesIncludes = options.seriesIncludes ?? "PLA Basic";
  const material = options.material ?? "PLA";
  const threshold = options.preferredDeltaThreshold ?? PREFERRED_DELTA_THRESHOLD;
  const allowSame = options.allowSameBrandFallback ?? true;
  const allowCross = options.allowCrossBrandFallback ?? true;

  const preferredPool = entries.filter((entry) =>
    inPool(entry, { brandSlug, seriesIncludes, material }),
  );
  const preferredRanked = rankPool(
    engineHex,
    preferredPool,
    "preferred_series",
    (entry, delta) =>
      `${brandSlug} · ${seriesIncludes} · CIEDE2000 最近（ΔE ${delta.toFixed(2)}）· ${displayName(entry)}`,
  );
  const preferred = preferredRanked[0];

  const sameBrandPool = entries.filter(
    (entry) =>
      inPool(entry, { brandSlug, material }) &&
      (preferred === undefined || entry.id !== preferred.entry.id),
  );
  const sameBrandRanked = allowSame
    ? rankPool(
        engineHex,
        sameBrandPool,
        "same_brand_fallback",
        (entry, delta) =>
          `${seriesIncludes} ΔE 超阈（>${threshold}）；同品牌 ${entry.s ?? "?"} 更近（ΔE ${delta.toFixed(2)}）· ${displayName(entry)}`,
      )
    : [];
  const sameBrand = sameBrandRanked[0];

  const crossPool = entries.filter(
    (entry) =>
      inPool(entry, { material }) &&
      entry.b !== brandSlug &&
      (preferred === undefined || entry.id !== preferred.entry.id) &&
      (sameBrand === undefined || entry.id !== sameBrand.entry.id),
  );
  const crossRanked = allowCross
    ? rankPool(
        engineHex,
        crossPool,
        "cross_brand_fallback",
        (entry, delta) =>
          `跨品牌备选（ΔE ${delta.toFixed(2)}）· ${entry.b} ${entry.s ?? ""} · ${displayName(entry)}`,
      )
    : [];
  const cross = crossRanked[0];

  if (preferred === undefined && sameBrand === undefined && cross === undefined) {
    return null;
  }

  let primary: RankedMatch;
  const alternates: RankedMatch[] = [];

  if (preferred !== undefined && preferred.delta_e <= threshold) {
    primary = preferred;
    if (sameBrand !== undefined && sameBrand.delta_e + 0.5 < preferred.delta_e) {
      alternates.push({
        ...sameBrand,
        match_reason: `同品牌更近备选（ΔE ${sameBrand.delta_e.toFixed(2)}）· ${displayName(sameBrand.entry)}`,
      });
    }
  } else if (
    sameBrand !== undefined &&
    (preferred === undefined || sameBrand.delta_e < preferred.delta_e)
  ) {
    primary = sameBrand;
    if (preferred !== undefined) {
      alternates.push({
        ...preferred,
        match_reason: `LUT 名义 ${seriesIncludes}（ΔE ${preferred.delta_e.toFixed(2)}，超阈 ${threshold}）· ${displayName(preferred.entry)}`,
      });
    }
  } else if (preferred !== undefined) {
    primary = preferred;
  } else if (sameBrand !== undefined) {
    primary = sameBrand;
  } else {
    primary = cross as RankedMatch;
  }

  // Cross-brand stays an alternate (AMS/LUT 优先同品牌)；仅在无同品牌可用时才作主推。
  if (cross !== undefined && cross.entry.id !== primary.entry.id) {
    if (primary.match_tier === "preferred_series" && primary.delta_e > threshold && sameBrand === undefined) {
      alternates.unshift({ ...primary, match_reason: primary.match_reason });
      primary = cross;
    } else if (cross.delta_e + 0.75 < primary.delta_e || primary.delta_e > threshold) {
      alternates.push(cross);
    }
  }

  // Deduplicate alternates by id, keep first 3.
  const seen = new Set<string>([primary.entry.id]);
  const uniqueAlts: RankedMatch[] = [];
  for (const alt of alternates) {
    if (seen.has(alt.entry.id)) continue;
    seen.add(alt.entry.id);
    uniqueAlts.push(alt);
    if (uniqueAlts.length >= 3) break;
  }

  return { primary, alternates: uniqueAlts };
}

export function recommendSlots(
  targets: SmokeSlotTarget[],
  entries: WebEntry[],
  options: RecommendOptions = {
    brandSlug: "bambu-lab",
    seriesIncludes: "PLA Basic",
    material: "PLA",
  },
): SlotRecommendation[] {
  const out: SlotRecommendation[] = [];
  for (const target of targets) {
    const match = recommendForHexCascaded(target.engine_hex, entries, options);
    if (match === null) continue;
    const { primary, alternates } = match;
    out.push({
      extruder: target.extruder,
      slot: target.slot,
      name_zh: target.name_zh,
      name_en: target.name_en,
      engine_hex: target.engine_hex,
      entry: primary.entry,
      catalog_hex: primary.catalog_hex,
      delta_e: primary.delta_e,
      purchase_url: primary.purchase_url,
      purchase_is_pdd: primary.purchase_is_pdd,
      match_tier: primary.match_tier,
      match_reason: primary.match_reason,
      alternates,
    });
  }
  return out;
}

export function toStackResult(input: {
  lutMode: StackLutMode;
  slots: SlotRecommendation[];
  previewRelpath?: string | null;
  model3mfRelpath?: string | null;
  previewDataUrl?: string | null;
  model3mfDataUrl?: string | null;
  createdAt?: string;
  note?: string;
}): StackResult {
  const createdAt =
    input.createdAt ??
    new Date().toLocaleString("sv-SE", { timeZone: "Asia/Tokyo" }).replace(" ", "T") + "+09:00";
  return {
    schema_version: 1,
    kind: "lumina-stack-result",
    created_at: createdAt,
    lut_mode: input.lutMode,
    source_job_kind: "lumina-stack-job",
    preview_relpath: input.previewRelpath ?? null,
    model_3mf_relpath: input.model3mfRelpath ?? null,
    preview_data_url: input.previewDataUrl ?? null,
    model_3mf_data_url: input.model3mfDataUrl ?? null,
    slots: input.slots.map((slot) => ({
      extruder: slot.extruder,
      slot: slot.slot,
      name_zh: slot.name_zh,
      name_en: slot.name_en,
      engine_hex: slot.engine_hex,
      recommended_id: slot.entry.id,
      recommended_hex: slot.catalog_hex,
      recommended_name: slot.entry.zh || slot.entry.en || slot.entry.id,
      delta_e: Number(slot.delta_e.toFixed(2)),
      purchase_url: slot.purchase_url,
      purchase_is_pdd: slot.purchase_is_pdd,
      match_tier: slot.match_tier,
      match_reason: slot.match_reason,
      alternates: slot.alternates.map((alt) => ({
        recommended_id: alt.entry.id,
        recommended_hex: alt.catalog_hex,
        recommended_name: alt.entry.zh || alt.entry.en || alt.entry.id,
        delta_e: Number(alt.delta_e.toFixed(2)),
        purchase_url: alt.purchase_url,
        purchase_is_pdd: alt.purchase_is_pdd,
        match_tier: alt.match_tier,
        match_reason: alt.match_reason,
      })),
    })),
    note:
      input.note ??
      "引擎槽位色按 CIEDE2000 在选色站目录内匹配；Preferred 系列 ΔE 超阈时回退同品牌/跨品牌并标清理由。GPL 叠色仍在本机 Lumina。",
  };
}
