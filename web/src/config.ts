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
