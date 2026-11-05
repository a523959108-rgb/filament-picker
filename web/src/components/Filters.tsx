import type { JSX } from "react";
import type { FilterState } from "../search";

export function Filters(props: {
  brands: { slug: string; name: string }[];
  families: string[];
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
