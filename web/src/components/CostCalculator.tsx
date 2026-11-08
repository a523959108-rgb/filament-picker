import { useState } from "react";
import type { JSX } from "react";
import { formatYuan, printCost } from "../cost";
import {
  COST_DEFAULT_GRAMS,
  COST_DEFAULT_HOURS,
  COST_DEFAULT_KWH_PRICE,
  COST_DEFAULT_PRICE_PER_KG,
  COST_DEFAULT_WATTS,
} from "../config";

const FIELDS = [
  { key: "grams", label: "用料（克）", defaultValue: COST_DEFAULT_GRAMS, step: "1" },
  { key: "pricePerKg", label: "耗材单价（元/千克）", defaultValue: COST_DEFAULT_PRICE_PER_KG, step: "0.1" },
  { key: "hours", label: "打印时长（小时）", defaultValue: COST_DEFAULT_HOURS, step: "0.1" },
  { key: "watts", label: "打印机功率（瓦）", defaultValue: COST_DEFAULT_WATTS, step: "1" },
  { key: "kwhPrice", label: "电价（元/千瓦时）", defaultValue: COST_DEFAULT_KWH_PRICE, step: "0.01" },
] as const;

type FieldKey = (typeof FIELDS)[number]["key"];

export function CostCalculator(): JSX.Element {
  const [values, setValues] = useState<Record<FieldKey, string>>({
    grams: String(COST_DEFAULT_GRAMS),
    pricePerKg: String(COST_DEFAULT_PRICE_PER_KG),
    hours: String(COST_DEFAULT_HOURS),
    watts: String(COST_DEFAULT_WATTS),
    kwhPrice: String(COST_DEFAULT_KWH_PRICE),
  });
  const cost = printCost({
    grams: Number(values.grams),
    pricePerKg: Number(values.pricePerKg),
    hours: Number(values.hours),
    watts: Number(values.watts),
    kwhPrice: Number(values.kwhPrice),
  });

  return (
    <section className="cost-calc" aria-label="打印成本">
      <h3>打印成本</h3>
      <p className="cost-formula">
        材料费 = 克数 ÷ 1000 × 每公斤价格；电费 = 时长 × 功率（千瓦） × 电价。
      </p>
      <div className="cost-fields">
        {FIELDS.map((field) => (
          <label key={field.key} className="field">
            <span className="field-label">{field.label}</span>
            <input
              type="number"
              min="0"
              step={field.step}
              inputMode="decimal"
              value={values[field.key]}
              onChange={(event) =>
                setValues((current) => ({ ...current, [field.key]: event.target.value }))
              }
            />
          </label>
        ))}
      </div>
      <dl className="cost-result">
        <div>
          <dt>材料费</dt>
          <dd>{formatYuan(cost.material)}</dd>
        </div>
        <div>
          <dt>电费</dt>
          <dd>{formatYuan(cost.energy)}</dd>
        </div>
        <div>
          <dt>合计</dt>
          <dd className="cost-total">{formatYuan(cost.total)}</dd>
        </div>
      </dl>
    </section>
  );
}
