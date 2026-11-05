import { describe, expect, it } from "vitest";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { FAMILIES } from "../config";
import {
  applyFilters,
  buildIndex,
  defaultOrder,
  EMPTY_FILTER,
  query,
} from "../search";
import type { FilterState } from "../search";
import type { WebCatalog } from "../types";

const catalog = sample as WebCatalog;
const index = buildIndex(catalog.entries);

function ids(entries: WebCatalog["entries"]): string[] {
  return entries.map((entry) => entry.id);
}

describe("catalog search", () => {
  it.each(["黑色", "hei", "hs", "30105"])("finds the official black entry for %s", (term) => {
    expect(ids(query(index, catalog, term, EMPTY_FILTER))).toEqual([
      "bambu-lab/petg-basic/black-30105",
    ]);
  });

  it("finds Sakura by English and Chinese names", () => {
    expect(ids(query(index, catalog, "sakura", EMPTY_FILTER))).toEqual([
      "byehassle/pla-ya-guang/sakura-bloom",
    ]);
    expect(ids(query(index, catalog, "樱花", EMPTY_FILTER))).toEqual([
      "byehassle/pla-ya-guang/sakura-bloom",
    ]);
  });

  it("finds the rainbow entry by code", () => {
    expect(ids(query(index, catalog, "rb009", EMPTY_FILTER))).toEqual([
      "cailab/rainbow-shift-pla/bamboo-rb009",
    ]);
  });

  it("orders an empty query by brand, series, and id", () => {
    expect(ids(query(index, catalog, "", EMPTY_FILTER))).toEqual([
      "bambu-lab/petg-basic/black-30105",
      "cailab/rainbow-shift-pla/bamboo-rb009",
      "esun/petg-basic/black",
      "byehassle/pla-ya-guang/sakura-bloom",
    ]);
    expect(ids(defaultOrder(catalog.entries, catalog.brands))).toEqual([
      "bambu-lab/petg-basic/black-30105",
      "cailab/rainbow-shift-pla/bamboo-rb009",
      "esun/petg-basic/black",
      "byehassle/pla-ya-guang/sakura-bloom",
    ]);
  });

  it("keeps both black entries for an English query", () => {
    expect(ids(query(index, catalog, "black", EMPTY_FILTER))).toEqual(
      expect.arrayContaining([
        "bambu-lab/petg-basic/black-30105",
        "esun/petg-basic/black",
      ]),
    );
  });

  it("applies material, hex, official, brand, and family filters", () => {
    expect(applyFilters(catalog.entries, { ...EMPTY_FILTER, materials: ["PETG"] })).toHaveLength(2);
    expect(applyFilters(catalog.entries, { ...EMPTY_FILTER, onlyHex: true })).toHaveLength(2);
    expect(
      applyFilters(catalog.entries, { ...EMPTY_FILTER, onlyOfficial: true }),
    ).toHaveLength(1);
    expect(
      applyFilters(catalog.entries, { ...EMPTY_FILTER, brands: ["esun"], materials: ["PLA"] }),
    ).toHaveLength(0);
    expect(ids(applyFilters(catalog.entries, { ...EMPTY_FILTER, families: ["粉"] }))).toEqual([
      "byehassle/pla-ya-guang/sakura-bloom",
    ]);
  });

  it("combines a query with an official-only filter", () => {
    const filter: FilterState = { ...EMPTY_FILTER, onlyOfficial: true };
    expect(ids(query(index, catalog, "黑色", filter))).toEqual([
      "bambu-lab/petg-basic/black-30105",
    ]);
  });

  it("uses all fifteen configured families", () => {
    expect(FAMILIES).toHaveLength(15);
  });
});
