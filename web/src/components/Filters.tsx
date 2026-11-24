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

  return (
    <div className="filters">
      <fieldset>
        <legend>品牌</legend>
        {props.brands.map((brand) => (
          <label key={brand.slug}>
            <input
              type="checkbox"
              checked={props.value.brands.includes(brand.slug)}
              onChange={() => props.onChange({ ...props.value, brands: toggle(props.value.brands, brand.slug) })}
            />
            {brand.name}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>材料</legend>
        {(["PLA", "PETG"] as const).map((material) => (
          <label key={material}>
            <input
              type="checkbox"
              checked={props.value.materials.includes(material)}
              onChange={() =>
                props.onChange({
                  ...props.value,
                  materials: props.value.materials.includes(material)
                    ? props.value.materials.filter((item) => item !== material)
                    : [...props.value.materials, material],
                })
              }
            />
            {material}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>色谱</legend>
        <div className="spectrum-row" role="group" aria-label="色谱">
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
        <fieldset>
          <legend>效果</legend>
          <div className="spectrum-row" role="group" aria-label="效果">
            {props.effects.map((effect) => (
              <button
                key={effect}
                type="button"
                className={props.value.effects.includes(effect) ? "spectrum-chip is-on" : "spectrum-chip"}
                aria-pressed={props.value.effects.includes(effect)}
                onClick={() => props.onChange({ ...props.value, effects: toggle(props.value.effects, effect) })}
              >
                {effect}
              </button>
            ))}
          </div>
        </fieldset>
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
