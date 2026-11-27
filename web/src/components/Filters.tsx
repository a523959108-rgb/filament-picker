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
  const brandLabel = props.brands.find((brand) => brand.slug === brandValue)?.name ?? "全部";
  return (
    <div className="filters">
      <fieldset>
        <legend className="visually-hidden">色谱</legend>
        <div className="spectrum-row" role="group" aria-label="色谱">
          <button
            type="button"
            className={props.value.families.length === 0 ? "spectrum-chip is-on" : "spectrum-chip"}
            aria-pressed={props.value.families.length === 0}
            onClick={() => props.onChange({ ...props.value, families: [] })}
          >
            <span className="spectrum-dot" style={{ background: "#d4e4fa" }} />
            <span>全色谱</span>
          </button>
          {props.families.map((family) => (
            <button
              key={family}
              type="button"
              className={props.value.families.includes(family) ? "spectrum-chip is-on" : "spectrum-chip"}
              aria-pressed={props.value.families.includes(family)}
              onClick={() => props.onChange({ ...props.value, families: toggle(props.value.families, family) })}
            >
              <span className={`spectrum-dot dot-${family.length}`} style={{ background: FAMILY_DOT[family] ?? "#64748b" }} />
              <span>{family}</span>
            </button>
          ))}
        </div>
      </fieldset>
      <div className="filter-chip-row">
        <label className="filter-chip">
          <span>品牌：{brandLabel}</span>
          <select aria-label="品牌" value={brandValue} onChange={(event) => {
            const value = event.target.value;
            props.onChange({ ...props.value, brands: value ? [value] : [] });
          }}>
            <option value="">全部</option>
            {props.brands.map((brand) => <option key={brand.slug} value={brand.slug}>{brand.name}</option>)}
          </select>
        </label>
        <label className="filter-chip">
          <span>材料：{materialValue || "全部"}</span>
          <select aria-label="材料" value={materialValue} onChange={(event) => {
            const value = event.target.value as "" | "PLA" | "PETG";
            props.onChange({ ...props.value, materials: value ? [value] : [] });
          }}>
            <option value="">全部</option>
            <option value="PLA">PLA</option>
            <option value="PETG">PETG</option>
          </select>
        </label>
        {props.effects.length > 0 && (
          <label className="filter-chip">
            <span>效果：{props.value.effects[0] || "全部"}</span>
            <select aria-label="效果" value={props.value.effects[0] ?? ""} onChange={(event) => {
              const value = event.target.value;
              props.onChange({ ...props.value, effects: value ? [value] : [] });
            }}>
              <option value="">全部</option>
              {props.effects.map((effect) => <option key={effect} value={effect}>{effect}</option>)}
            </select>
          </label>
        )}
        <label className={props.value.onlyOfficial ? "filter-chip is-on" : "filter-chip"}>
          <input
            type="checkbox"
            checked={props.value.onlyOfficial}
            onChange={() => props.onChange({ ...props.value, onlyOfficial: !props.value.onlyOfficial })}
          />
          只看官方色
        </label>
        <label className={props.value.onlyHex ? "filter-chip is-on" : "filter-chip"}>
          <input
            type="checkbox"
            checked={props.value.onlyHex}
            onChange={() => props.onChange({ ...props.value, onlyHex: !props.value.onlyHex })}
          />
          只看有色值
        </label>
      </div>
    </div>
  );
}

const FAMILY_DOT: Record<string, string> = {
  "黑白灰": "#e2e8f0",
  "多色/渐变": "#f59e0b",
  "绿": "#65a30d",
  "蓝": "#0284c7",
  "金属/金银铜": "#d6b25e",
  "透明": "#f8fafc",
  "红": "#e11d48",
  "棕/米/肤": "#a16207",
  "粉": "#f472b6",
  "黄": "#eab308",
  "紫": "#7c3aed",
  "橙": "#ea580c",
  "木/石/大理石": "#78716c",
  "夜光": "#4ade80",
  "其他": "#64748b",
};
