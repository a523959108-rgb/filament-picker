import type { JSX } from "react";
import type { WebEntry } from "../types";

export function SwatchGrid({
  entries,
  brands,
  onSelect,
}: {
  entries: WebEntry[];
  brands: { slug: string; name: string }[];
  onSelect?: (id: string) => void;
}): JSX.Element {
  const brandNames = new Map(brands.map((brand) => [brand.slug, brand.name]));
  return (
    <section>
      <p className="catalog-count">共 {entries.length} 个颜色</p>
      <div className="swatch-grid">
        {entries.map((entry) => {
          const className = entry.hex.length === 0 ? "swatch swatch-empty" : "swatch";
          const style = entry.hex.length === 0 ? undefined : { backgroundColor: entry.hex[0] };
          return (
            <button className="swatch-card" key={entry.id} onClick={() => onSelect?.(entry.id)}>
              <span className={className} style={style} aria-label={entry.hex[0] ?? "无色值"} />
              <span className="swatch-name">
                {brandNames.get(entry.b) ?? entry.b} {entry.s}
              </span>
              <span className="swatch-color">{entry.zh ?? entry.en}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
