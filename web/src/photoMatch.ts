/**
 * Nearest purchasable SKUs for a photo color, plus a RYBW tray-mix estimate
 * when no single spool is close enough. CIEDE2000 comes from ./color (culori).
 * The mix is a linear-light preview of the existing four-color tray — not the
 * local Lumina LUT.
 */

import { converter, formatHex, parse } from "culori";
import { hexDelta, isApproxSource } from "./color";
import { SIMILAR_EXCLUDE_EFFECTS } from "./config";
import { pickPurchaseUrl } from "./stackRecommend";
import type { WebEntry } from "./types";
import trayMap from "../public/four-color-tray-map.json";

/** Same cutoff as backend MATCH_MAX_DE and the similar-color list. */
export const PHOTO_CLOSE_DE = 10;

const toLinear = converter("lrgb");
const excluded = new Set<string>(SIMILAR_EXCLUDE_EFFECTS);

export type PhotoSkuMatch = {
  entry: WebEntry;
  brandName: string;
  series: string;
  name: string;
  hex: string;
  delta: number;
  label: "几乎一样" | "接近" | "勉强" | "偏远";
  price: string | null;
  purchaseUrl: string | null;
  isApprox: boolean;
};

export type StackBase = {
  slot: string;
  name_zh: string;
  hex: string;
  catalog_id: string;
};

export type StackPart = StackBase & { weight: number };

export type StackSuggestion = {
  mode: "RYBW";
  mixedHex: string;
  delta: number;
  parts: StackPart[];
};

type TraySlot = { slot: string; name_zh: string; hex: string; catalog_id: string };

export const RYBW_STACK_BASES: StackBase[] = (
  trayMap.palettes.RYBW.slots as TraySlot[]
).map((slot) => ({
  slot: slot.slot,
  name_zh: slot.name_zh,
  hex: slot.hex.toUpperCase(),
  catalog_id: slot.catalog_id,
}));

export function deltaLabel(delta: number): PhotoSkuMatch["label"] {
  if (delta < 2) return "几乎一样";
  if (delta < 5) return "接近";
  if (delta <= PHOTO_CLOSE_DE) return "勉强";
  return "偏远";
}

export function singleIsClose(matches: readonly { delta: number }[]): boolean {
  const best = matches[0];
  return best !== undefined && best.delta <= PHOTO_CLOSE_DE;
}

function brandName(slug: string, brands: { slug: string; name: string }[]): string {
  return brands.find((brand) => brand.slug === slug)?.name ?? slug;
}

function displayName(entry: WebEntry): string {
  const base = [entry.zh, entry.en].filter((value): value is string => Boolean(value)).join(" ");
  const text = base || entry.id;
  return entry.code ? `${text}（${entry.code}）` : text;
}

function isCandidate(entry: WebEntry): boolean {
  if (entry.hex.length !== 1) return false;
  const hex = entry.hex[0];
  if (hex === undefined || !/^#[0-9A-Fa-f]{6}$/.test(hex)) return false;
  return !entry.eff.some((effect) => excluded.has(effect));
}

/** Closest catalog colors by CIEDE2000. Purchase URL breaks ties, then id. */
export function nearestSkus(
  hex: string,
  entries: readonly WebEntry[],
  brands: readonly { slug: string; name: string }[],
  limit = 4,
): PhotoSkuMatch[] {
  return entries
    .filter(isCandidate)
    .map((entry) => {
      const catalogHex = entry.hex[0] as string;
      const purchase = pickPurchaseUrl(entry);
      return {
        entry,
        brandName: brandName(entry.b, [...brands]),
        series: entry.s,
        name: displayName(entry),
        hex: catalogHex,
        delta: hexDelta(hex, catalogHex),
        label: "偏远" as const,
        price: entry.price,
        purchaseUrl: purchase.url,
        isApprox: isApproxSource(entry.src),
      };
    })
    .sort(
      (a, b) =>
        a.delta - b.delta ||
        Number(a.purchaseUrl === null) - Number(b.purchaseUrl === null) ||
        a.entry.id.localeCompare(b.entry.id),
    )
    .slice(0, limit)
    .map((match) => ({ ...match, label: deltaLabel(match.delta) }));
}

function linearOf(hex: string): [number, number, number] | null {
  const parsed = parse(hex);
  if (parsed === undefined) return null;
  const linear = toLinear(parsed);
  if (linear.r === undefined || linear.g === undefined || linear.b === undefined) return null;
  return [linear.r, linear.g, linear.b];
}

function weightTable(n: number, steps: number): number[][] {
  const out: number[][] = [];
  const current = new Array<number>(n).fill(0);
  const walk = (index: number, remaining: number) => {
    if (index === n - 1) {
      current[index] = remaining / steps;
      out.push([...current]);
      return;
    }
    for (let take = 0; take <= remaining; take += 1) {
      current[index] = take / steps;
      walk(index + 1, remaining - take);
    }
  };
  walk(0, steps);
  return out;
}

const WEIGHTS_4 = weightTable(4, 10);

function mixHex(channels: [number, number, number][], weights: number[]): string | null {
  let r = 0;
  let g = 0;
  let b = 0;
  for (let i = 0; i < channels.length; i += 1) {
    const channel = channels[i];
    const weight = weights[i] ?? 0;
    if (channel === undefined) return null;
    r += weight * channel[0];
    g += weight * channel[1];
    b += weight * channel[2];
  }
  const hex = formatHex({ mode: "lrgb", r, g, b });
  return hex === undefined ? null : hex.toUpperCase();
}

/**
 * Coarse linear-light mix of the RYBW tray colors (10% steps).
 * Returns null when the target hex cannot be parsed.
 */
export function suggestStack(targetHex: string, bases: readonly StackBase[] = RYBW_STACK_BASES): StackSuggestion | null {
  if (bases.length === 0) return null;
  const target = linearOf(targetHex);
  if (target === null) return null;
  const channels = bases.map((base) => linearOf(base.hex));
  if (channels.some((channel) => channel === null)) return null;
  const linear = channels as [number, number, number][];
  const tables = bases.length === 4 ? WEIGHTS_4 : weightTable(bases.length, 10);
  let best: { delta: number; hex: string; weights: number[] } | null = null;
  for (const weights of tables) {
    const hex = mixHex(linear, weights);
    if (hex === null) continue;
    const delta = hexDelta(targetHex, hex);
    const inks = weights.filter((weight) => weight > 0).length;
    if (best === null) {
      best = { delta, hex, weights };
      continue;
    }
    const bestInks = best.weights.filter((weight) => weight > 0).length;
    const closer = delta + 0.05 < best.delta;
    const simpler = Math.abs(delta - best.delta) <= 0.05 && inks < bestInks;
    if (closer || simpler) best = { delta, hex, weights };
  }
  if (best === null) return null;
  const parts = bases
    .map((base, index) => ({
      ...base,
      weight: Math.round((best.weights[index] ?? 0) * 10) / 10,
    }))
    .filter((part) => part.weight > 0)
    .sort((a, b) => b.weight - a.weight || a.slot.localeCompare(b.slot));
  return { mode: "RYBW", mixedHex: best.hex, delta: best.delta, parts };
}
