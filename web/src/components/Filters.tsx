import type { JSX } from "react";
import type { FilterState } from "../search";

export function Filters(props: {
  brands: { slug: string; name: string }[];
  families: string[];
  effects: string[];
  value: FilterState;
  onChange: (f: FilterState) => void;
}): JSX.Element {
  const toggle = (values: string[], value: string): string[] =>
    values.includes(value) ? values.filter((item) => item !== value) : [...values, value];

  const brandValue = props.value.brands.length === 1 ? props.value.brands[0] : "";
  const materialValue = props.value.materials.length === 1 ? props.value.materials[0] : "";
  return (
    <div className="filters">
      <div className="filter-selects">
        <label>品牌
          <select aria-label="品牌" value={brandValue} onChange={(event) => {
            const value = event.target.value;
            props.onChange({ ...props.value, brands: value ? [value] : [] });
          }}>
            <option value="">全部</option>
            {props.brands.map((brand) => <option key={brand.slug} value={brand.slug}>{brand.name}</option>)}
          </select>
        </label>
        <label>材料
          <select aria-label="材料" value={materialValue} onChange={(event) => {
            const value = event.target.value as "" | "PLA" | "PETG";
            props.onChange({ ...props.value, materials: value ? [value] : [] });
          }}>
            <option value="">全部</option>
            <option value="PLA">PLA</option>
            <option value="PETG">PETG</option>
          </select>
        </label>
      </div>
      <fieldset>
        <legend>色谱</legend>
        <div className="spectrum-row" role="group" aria-label="色谱" style={{ display: "flex", flexWrap: "nowrap", overflowX: "auto" }}>
          {props.families.map((family) => (
            <button
              key={family}
              type="button"
              className={props.value.families.includes(family) ? "spectrum-chip is-on" : "spectrum-chip"}
              aria-pressed={props.value.families.includes(family)}
              onClick={() => props.onChange({ ...props.value, families: toggle(props.value.families, family) })}
            >
              {family}
            </button>
          ))}
        </div>
      </fieldset>
      {props.effects.length > 0 && (
        <label className="filter-selects">效果
          <select aria-label="效果" value={props.value.effects[0] ?? ""} onChange={(event) => {
            const value = event.target.value;
            props.onChange({ ...props.value, effects: value ? [value] : [] });
          }}>
            <option value="">全部</option>
            {props.effects.map((effect) => <option key={effect} value={effect}>{effect}</option>)}
          </select>
        </label>
      )}
      <label>
        <input
          type="checkbox"
          checked={props.value.onlyHex}
          onChange={() => props.onChange({ ...props.value, onlyHex: !props.value.onlyHex })}
        />
        只看有色值
      </label>
      <label>
        <input
          type="checkbox"
          checked={props.value.onlyOfficial}
          onChange={() => props.onChange({ ...props.value, onlyOfficial: !props.value.onlyOfficial })}
        />
        只看官方色
      </label>
    </div>
  );
}
