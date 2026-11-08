import { describe, expect, it } from "vitest";
import { formatYuan, printCost } from "../cost";
import {
  COST_DEFAULT_GRAMS,
  COST_DEFAULT_HOURS,
  COST_DEFAULT_KWH_PRICE,
  COST_DEFAULT_PRICE_PER_KG,
  COST_DEFAULT_WATTS,
} from "../config";

describe("print cost", () => {
  it("uses grams per kilogram and watts as kilowatts", () => {
    const cost = printCost({
      grams: COST_DEFAULT_GRAMS,
      pricePerKg: COST_DEFAULT_PRICE_PER_KG,
      hours: COST_DEFAULT_HOURS,
      watts: COST_DEFAULT_WATTS,
      kwhPrice: COST_DEFAULT_KWH_PRICE,
    });
    expect(cost.material).toBeCloseTo(3.5);
    expect(cost.energy).toBeCloseTo(0.36);
    expect(cost.total).toBeCloseTo(3.86);
    expect(formatYuan(cost.total)).toBe("3.86 元");
  });

  it("treats blank or negative inputs as zero", () => {
    const cost = printCost({
      grams: Number(""),
      pricePerKg: -5,
      hours: Number.NaN,
      watts: 100,
      kwhPrice: 1,
    });
    expect(cost.total).toBe(0);
  });
});
