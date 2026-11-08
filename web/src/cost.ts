export interface CostInput {
  grams: number;
  pricePerKg: number;
  hours: number;
  watts: number;
  kwhPrice: number;
}

export interface CostBreakdown {
  material: number;
  energy: number;
  total: number;
}

/**
 * 材料费 = 克数 / 1000 × 每公斤价格
 * 电费 = 时长（小时） × 功率（千瓦） × 电价（元/千瓦时）
 */
export function printCost(input: CostInput): CostBreakdown {
  const grams = nonNegative(input.grams);
  const pricePerKg = nonNegative(input.pricePerKg);
  const hours = nonNegative(input.hours);
  const watts = nonNegative(input.watts);
  const kwhPrice = nonNegative(input.kwhPrice);
  const material = (grams / 1000) * pricePerKg;
  const energy = hours * (watts / 1000) * kwhPrice;
  return { material, energy, total: material + energy };
}

export function formatYuan(value: number): string {
  return `${value.toFixed(2)} 元`;
}

function nonNegative(value: number): number {
  if (!Number.isFinite(value) || value < 0) return 0;
  return value;
}
