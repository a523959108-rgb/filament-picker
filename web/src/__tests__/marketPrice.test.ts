import { describe, expect, it } from "vitest";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import {
  isPddGoodsUrl,
  listGoodsOffers,
  parseCnySpoolYuan,
  spoolYuanAsPricePerKg,
  summarizeMarketPrices,
} from "../marketPrice";
import type { WebCatalog } from "../types";

describe("marketPrice", () => {
  it("detects pinduoduo goods urls and rejects search pages", () => {
    expect(isPddGoodsUrl("https://mobile.pinduoduo.com/goods.html?goods_id=931315367733")).toBe(
      true,
    );
    expect(
      isPddGoodsUrl("https://mobile.pinduoduo.com/search_result.html?search_key=%E6%8B%93%E7%AB%B9"),
    ).toBe(false);
    expect(isPddGoodsUrl("https://mobile.pinduoduo.com/goods.html?goods_id=not-real")).toBe(false);
  });

  it("parses CNY spool card prices and skips JPY/USD", () => {
    expect(parseCnySpoolYuan("¥34.5 CNY（商品卡价，非单色价）")).toBeCloseTo(34.5);
    expect(parseCnySpoolYuan("¥2,400起 JPY")).toBeNull();
    expect(parseCnySpoolYuan("US$19.99")).toBeNull();
    expect(parseCnySpoolYuan(null)).toBeNull();
    expect(parseCnySpoolYuan("")).toBeNull();
  });

  it("lists goods offers from the sample catalog and summarizes gaps", () => {
    const catalog = sample as WebCatalog;
    const rows = listGoodsOffers(catalog.entries);
    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("byehassle/pla-ya-guang/sakura-bloom");
    expect(rows[0].cnyYuan).toBeCloseTo(34.5);
    expect(spoolYuanAsPricePerKg(rows[0].cnyYuan!)).toBeCloseTo(34.5);

    const missing = listGoodsOffers([
      {
        ...catalog.entries[0],
        id: "bambu-lab/pla-basic/black-10101",
        url: "https://mobile.pinduoduo.com/goods.html?goods_id=646322960873",
        price: null,
      },
    ]);
    const summary = summarizeMarketPrices([...rows, ...missing]);
    expect(summary.goodsCount).toBe(2);
    expect(summary.withPriceText).toBe(1);
    expect(summary.missingPriceText).toBe(1);
    expect(summary.minCny).toBeCloseTo(34.5);
    expect(summary.gapNote).toContain("暂无报价");
  });
});
