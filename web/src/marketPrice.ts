import type { WebEntry } from "./types";

const PDD_HOSTS = new Set([
  "mobile.pinduoduo.com",
  "pinduoduo.com",
  "www.pinduoduo.com",
  "mobile.yangkeduo.com",
  "yangkeduo.com",
  "www.yangkeduo.com",
]);

export interface GoodsOfferRow {
  id: string;
  brandSlug: string;
  brandLabel: string;
  series: string;
  name: string;
  url: string;
  priceText: string | null;
  /** Parsed CNY spool card price, when recognizable. */
  cnyYuan: number | null;
}

export interface MarketPriceSummary {
  goodsCount: number;
  withPriceText: number;
  missingPriceText: number;
  cnyParsable: number;
  minCny: number | null;
  maxCny: number | null;
  medianCny: number | null;
  /** Human note about data gaps / assumptions. */
  gapNote: string;
}

function parseUrl(url: string): URL | null {
  try {
    return new URL(url.trim());
  } catch {
    return null;
  }
}

/** True for a Pinduoduo/Yangkeduo goods page with a numeric goods_id. */
export function isPddGoodsUrl(url: string): boolean {
  const parsed = parseUrl(url);
  if (parsed === null) return false;
  const host = parsed.hostname.toLowerCase();
  if (!PDD_HOSTS.has(host) || !parsed.pathname.toLowerCase().includes("goods")) {
    return false;
  }
  return [...parsed.searchParams.getAll("goods_id")].some((value) => /^\d+$/.test(value));
}

/**
 * Parse a CNY spool card price from offer price_text.
 * Accepts texts that mark CNY / 元 / 商品卡价. Rejects clear JPY/USD store quotes.
 * Assumption for cost fill: card yuan ≈ 元/千克（常见 1kg 卷；未写净重时不当真公斤价）。
 */
export function parseCnySpoolYuan(priceText: string | null | undefined): number | null {
  if (priceText == null) return null;
  const text = priceText.trim();
  if (text === "") return null;
  if (/JPY|USD|US\s*\$|\$/i.test(text) && !/CNY|人民币|商品卡/.test(text)) {
    return null;
  }
  if (!/CNY|人民币|元|商品卡/i.test(text) && !/¥|￥/.test(text)) {
    return null;
  }
  // Prefer the first plain number after currency mark; strip thousands commas.
  const normalized = text.replace(/,/g, "");
  const match = normalized.match(/(?:¥|￥)?\s*(\d+(?:\.\d+)?)/);
  if (match === null) return null;
  const value = Number(match[1]);
  if (!Number.isFinite(value) || value <= 0) return null;
  // Guard: JP store quotes like 2400 without CNY marker already rejected; still drop huge CNY outliers.
  if (value > 500) return null;
  return value;
}

/** Treat recognized CNY spool card price as 元/千克 for the cost form (1kg spool assumption). */
export function spoolYuanAsPricePerKg(cnyYuan: number): number {
  return cnyYuan;
}

export function listGoodsOffers(entries: WebEntry[]): GoodsOfferRow[] {
  const rows: GoodsOfferRow[] = [];
  for (const entry of entries) {
    if (!isPddGoodsUrl(entry.url)) continue;
    const name = entry.zh || entry.en || entry.code || entry.id;
    rows.push({
      id: entry.id,
      brandSlug: entry.b,
      brandLabel: entry.b,
      series: entry.s,
      name,
      url: entry.url,
      priceText: entry.price,
      cnyYuan: parseCnySpoolYuan(entry.price),
    });
  }
  return rows;
}

export function summarizeMarketPrices(rows: GoodsOfferRow[]): MarketPriceSummary {
  const withPriceText = rows.filter((row) => row.priceText != null && row.priceText.trim() !== "").length;
  const cnyValues = rows
    .map((row) => row.cnyYuan)
    .filter((value): value is number => value != null)
    .sort((a, b) => a - b);
  const missingPriceText = rows.length - withPriceText;
  const gapParts: string[] = [];
  if (missingPriceText > 0) {
    gapParts.push(
      `${missingPriceText} 条真链尚无 price_text（多为拓竹 batch1：采集时只写了 goods_id）。展示用「暂无报价」占位，计算器仍用默认 ${70} 元/千克。`,
    );
  }
  gapParts.push(
    "有 CNY/商品卡价时按「约 1kg 卷卡价 ≈ 元/千克」填入计算器；JPY/USD 店报价不自动换算。",
  );
  return {
    goodsCount: rows.length,
    withPriceText,
    missingPriceText,
    cnyParsable: cnyValues.length,
    minCny: cnyValues.length ? cnyValues[0] : null,
    maxCny: cnyValues.length ? cnyValues[cnyValues.length - 1] : null,
    medianCny: cnyValues.length ? cnyValues[Math.floor(cnyValues.length / 2)] : null,
    gapNote: gapParts.join(" "),
  };
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through
  }
  return false;
}
