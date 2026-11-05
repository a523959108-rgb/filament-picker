import { differenceCiede2000 } from "culori";
import type { WebEntry } from "./types";

const MAX_SIMILAR_DELTA = 10;

export function hexDelta(a: string, b: string): number {
  return differenceCiede2000()(a, b);
}

export function similar(
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
