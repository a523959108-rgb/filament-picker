import type { JSX } from "react";
import type { FilterState } from "../search";

const EFFECT_LABELS: Record<string, string> = {
  matte: "哑光 matte",
  silk: "丝绸 silk",
  metallic: "金属 metallic",
  cf: "碳纤 cf",
  gf: "玻纤 gf",
  translucent: "透明 translucent",
  glow: "夜光 glow",
  sparkle: "闪粉 sparkle",
  gradient: "渐变 gradient",
  multi: "多色 multi",
  dual: "双色 dual",
  tri: "三色 tri",
  marble: "大理石 marble",
  wood: "木质 wood",
  color_change: "变色 color_change",
};

export function Filters(props: {
  brands: { slug: string; name: string }[];
  families: string[];
  effects?: string[];
  value: FilterState;
  hasActive?: boolean;
  onReset?: () => void;
  onChange: (f: FilterState) => void;
}): JSX.Element {
  const toggle = (values: string[], value: string): string[] =>
    values.includes(value) ? values.filter((item) => item !== value) : [...values, value];

  return (
    <div className="filters">
      {props.hasActive && props.onReset ? (
        <button type="button" className="btn btn-ghost filters-reset" onClick={props.onReset}>
          清空筛选
        </button>
      ) : null}
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
        <legend>色系</legend>
        {props.families.map((family) => (
          <label key={family}>
            <input
              type="checkbox"
              checked={props.value.families.includes(family)}
              onChange={() => props.onChange({ ...props.value, families: toggle(props.value.families, family) })}
            />
            {family}
          </label>
        ))}
      </fieldset>
      {props.effects && props.effects.length > 0 ? (
        <fieldset>
          <legend>效果</legend>
          {props.effects.map((effect) => (
            <label key={effect}>
              <input
                type="checkbox"
                checked={props.value.effects.includes(effect)}
                onChange={() =>
                  props.onChange({ ...props.value, effects: toggle(props.value.effects, effect) })
                }
              />
              {EFFECT_LABELS[effect] ?? effect}
            </label>
          ))}
        </fieldset>
      ) : null}
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
