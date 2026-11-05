import MiniSearch from "minisearch";
import type { WebCatalog, WebEntry } from "./types";

export interface FilterState {
  brands: string[];
  materials: ("PLA" | "PETG")[];
  families: string[];
  onlyHex: boolean;
  onlyOfficial: boolean;
}

export const EMPTY_FILTER: FilterState = {
  brands: [],
  materials: [],
  families: [],
  onlyHex: false,
  onlyOfficial: false,
};

export function buildIndex(entries: WebEntry[]): MiniSearch<WebEntry> {
  const index = new MiniSearch<WebEntry>({
    fields: ["en", "zh", "py", "pyi", "code", "b", "s"],
    storeFields: ["id"],
    searchOptions: {
      prefix: true,
      fuzzy: 0.2,
      boost: { zh: 2, en: 2, code: 3 },
    },
  });
  index.addAll(entries);
  return index;
}

export function defaultOrder(entries: WebEntry[], brands: { slug: string }[]): WebEntry[] {
  const brandOrder = new Map(brands.map((brand, index) => [brand.slug, index]));
  return [...entries].sort((left, right) => {
    const brandDifference =
      (brandOrder.get(left.b) ?? brands.length) - (brandOrder.get(right.b) ?? brands.length);
    if (brandDifference !== 0) return brandDifference;
    const seriesDifference = left.s.localeCompare(right.s, "zh");
    if (seriesDifference !== 0) return seriesDifference;
    return left.id.localeCompare(right.id);
  });
}

export function applyFilters(entries: WebEntry[], f: FilterState): WebEntry[] {
  return entries.filter((entry) => {
    const brandMatches = f.brands.length === 0 || f.brands.includes(entry.b);
    const materialMatches = f.materials.length === 0 || f.materials.includes(entry.m);
    const familyMatches = f.families.length === 0 || f.families.includes(entry.fam);
    const hexMatches = !f.onlyHex || entry.hex.length > 0;
    const officialMatches = !f.onlyOfficial || entry.src === "official";
    return brandMatches && materialMatches && familyMatches && hexMatches && officialMatches;
  });
}

export function query(
  index: MiniSearch<WebEntry>,
  catalog: WebCatalog,
  q: string,
  f: FilterState,
): WebEntry[] {
  const trimmed = q.trim();
  if (trimmed === "") {
    return applyFilters(defaultOrder(catalog.entries, catalog.brands), f);
  }

  const entriesById = new Map(catalog.entries.map((entry) => [entry.id, entry]));
  const results = index.search(trimmed);
  const entries = results
    .sort((left, right) => right.score - left.score)
    .map((result) => entriesById.get(String(result.id)))
    .filter((entry): entry is WebEntry => entry !== undefined);
  return applyFilters(entries, f);
}
