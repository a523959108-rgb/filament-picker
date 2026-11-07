import { differenceCiede2000, differenceEuclidean } from "culori";
import {
  SIMILAR_EXCLUDE_EFFECTS,
  SIMILAR_PREFERRED_EFFECTS,
} from "./config";
import type { WebEntry } from "./types";

const MAX_SIMILAR_DELTA = 10;
const EFFECT_MISMATCH_PENALTY = 0.75;

const excludeEffects = new Set<string>(SIMILAR_EXCLUDE_EFFECTS);
const preferredEffects = new Set<string>(SIMILAR_PREFERRED_EFFECTS);

const ciede2000 = differenceCiede2000();
const oklabDistance = differenceEuclidean("oklab");

export type SimilarMatch = {
  entry: WebEntry;
  delta: number;
  oklab: number;
  isApprox: boolean;
};

export function hexDelta(a: string, b: string): number {
  return ciede2000(a, b);
}

/** OKLab Euclidean distance — used as a tie-breaker after CIEDE2000. */
export function hexDeltaOklab(a: string, b: string): number {
  return oklabDistance(a, b);
}

export function isApproxSource(src: WebEntry["src"]): boolean {
  return src === "store_swatch" || src === "image_extracted";
}

export function isSimilarComparable(entry: WebEntry): boolean {
  if (entry.hex.length !== 1) return false;
  return !entry.eff.some((effect) => excludeEffects.has(effect));
}

function preferredOverlap(a: string[], b: string[]): boolean {
  for (const effect of a) {
    if (preferredEffects.has(effect) && b.includes(effect)) return true;
  }
  return false;
}

function hasPreferred(effects: string[]): boolean {
  return effects.some((effect) => preferredEffects.has(effect));
}

function effectPenalty(target: WebEntry, candidate: WebEntry): number {
  if (!hasPreferred(target.eff)) return 0;
  return preferredOverlap(target.eff, candidate.eff) ? 0 : EFFECT_MISMATCH_PENALTY;
}

/**
 * Cross-brand similar colors.
 * Primary metric: Culori CIEDE2000 (OKLab-friendly pipeline).
 * Tie-break: OKLab Euclidean distance, then id.
 * Special finishes (silk/transparent/gradient/…): excluded or same-finish preferred.
 */
export function similar(
  target: WebEntry,
  entries: WebEntry[],
  limit: number = 8,
): SimilarMatch[] {
  if (!isSimilarComparable(target)) {
    return [];
  }
  const targetHex = target.hex[0];
  if (targetHex === undefined) {
    return [];
  }

  return entries
    .filter((entry) => entry.id !== target.id && isSimilarComparable(entry))
    .map((entry) => {
      const otherHex = entry.hex[0] as string;
      const delta = hexDelta(targetHex, otherHex) + effectPenalty(target, entry);
      const oklab = hexDeltaOklab(targetHex, otherHex);
      return {
        entry,
        delta,
        oklab,
        isApprox: isApproxSource(entry.src) || isApproxSource(target.src),
      };
    })
    .filter(({ delta }) => delta <= MAX_SIMILAR_DELTA)
    .sort(
      (a, b) =>
        a.delta - b.delta ||
        a.oklab - b.oklab ||
        a.entry.id.localeCompare(b.entry.id),
    )
    .slice(0, limit);
}

/** Legacy CIEDE2000-only matcher kept for A/B comparison tests. */
export function similarLegacy(
  target: WebEntry,
  entries: WebEntry[],
  limit: number = 8,
): { entry: WebEntry; delta: number }[] {
  if (target.hex.length !== 1 || target.eff.includes("multi")) {
    return [];
  }
  const targetHex = target.hex[0];
  if (targetHex === undefined) {
    return [];
  }
  return entries
    .filter(
      (entry) =>
        entry.id !== target.id && entry.hex.length === 1 && !entry.eff.includes("multi"),
    )
    .map((entry) => ({ entry, delta: hexDelta(targetHex, entry.hex[0] as string) }))
    .filter(({ delta }) => delta <= MAX_SIMILAR_DELTA)
    .sort((a, b) => a.delta - b.delta || a.entry.id.localeCompare(b.entry.id))
    .slice(0, limit);
}

export function sourceBadge(src: WebEntry["src"], conf: number | null): string {
  switch (src) {
    case "official":
      return "官方色值";
    case "store_swatch":
      return "店铺示意色（近似）";
    case "image_extracted":
      return `商品图取色（近似，置信度 ${(conf ?? 0).toFixed(2)}）`;
    case "manual":
      return "人工校对";
    default:
      return "无色值";
  }
}
