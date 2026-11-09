export const CATALOG_URL = "./web-catalog.json";

/** Print-cost calculator defaults. Editable in the form; not fetched. */
export const COST_DEFAULT_GRAMS = 50;
export const COST_DEFAULT_PRICE_PER_KG = 70;
export const COST_DEFAULT_HOURS = 3;
export const COST_DEFAULT_WATTS = 200;
export const COST_DEFAULT_KWH_PRICE = 0.6;

/** First paint swatch count; more load on demand. */
export const SWATCH_PAGE_SIZE = 48;

/**
 * Effects whose hex is unreliable for cross-brand matching
 * (aligned with backend MATCH_EXCLUDE_EFFECTS in SPEC §8).
 */
export const SIMILAR_EXCLUDE_EFFECTS = [
  "multi",
  "dual",
  "tri",
  "gradient",
  "color_change",
  "translucent",
  "glow",
  "sparkle",
  "marble",
  "wood",
] as const;

/** Prefer matching within the same finish when both sides carry it. */
export const SIMILAR_PREFERRED_EFFECTS = ["silk", "metallic", "matte", "cf", "gf"] as const;

export const FAMILIES = [
  "黑白灰",
  "多色/渐变",
  "绿",
  "蓝",
  "金属/金银铜",
  "透明",
  "红",
  "棕/米/肤",
  "粉",
  "黄",
  "紫",
  "橙",
  "木/石/大理石",
  "夜光",
  "其他",
] as const;

/** Production stack subdomain origin (no trailing slash). */
export const STACK_SITE_ORIGIN = "https://stack.filament.ibaozi.com";

/** Main catalog host; on this host the stack CTA opens the subdomain. */
export const MAIN_SITE_HOST = "filament.ibaozi.com";

/** In-app hash for the stack page (local / same-host fallback). */
export const STACK_HASH = "#/stack";

export function stackHostFromOrigin(origin: string = STACK_SITE_ORIGIN): string {
  try {
    return new URL(origin).hostname;
  } catch {
    return "";
  }
}

export function isStackHost(hostname: string): boolean {
  const stackHost = stackHostFromOrigin();
  return stackHost !== "" && hostname === stackHost;
}

/**
 * Where the homepage / nav "叠色" entry should go.
 * - Main production host → stack subdomain `/#/stack`
 * - Already on stack host, or local/preview → in-app `#/stack`
 */
export function stackEntryHref(hostname: string): string {
  if (!STACK_SITE_ORIGIN) return STACK_HASH;
  if (isStackHost(hostname)) return STACK_HASH;
  if (hostname === MAIN_SITE_HOST) return `${STACK_SITE_ORIGIN}/${STACK_HASH}`;
  return STACK_HASH;
}
