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
    <section className="swatch-section">
      <p className="catalog-count" aria-live="polite">
        共 {entries.length} 个颜色
      </p>
      {entries.length === 0 ? (
        <div className="panel empty-state">
          <p>没有符合条件的颜色</p>
          <p className="empty-hint">试试减少筛选条件或换个关键词</p>
        </div>
      ) : (
        <div className="swatch-grid">
          {entries.map((entry) => {
            const hasImg = Boolean(entry.img);
            const hasHex = entry.hex.length > 0;
            const className = [
              "swatch",
              !hasImg && !hasHex ? "swatch-empty" : "",
              hasImg ? "swatch-has-img" : "",
            ]
              .filter(Boolean)
              .join(" ");
            const style =
              !hasImg && hasHex ? { backgroundColor: entry.hex[0] } : undefined;
            return (
              <button
                className="swatch-card"
                key={entry.id}
                onClick={() => onSelect?.(entry.id)}
              >
                <span
                  className={className}
                  style={style}
                  aria-label={entry.hex[0] ?? (hasImg ? "SKU 图片" : "无色值")}
                >
                  {hasImg ? (
                    <img
                      className="swatch-img"
                      src={entry.img!}
                      alt=""
                      loading="lazy"
                    />
                  ) : null}
                  {hasImg && hasHex ? (
                    <span
                      className="swatch-hex-dot"
                      style={{ backgroundColor: entry.hex[0] }}
                      title={entry.hex[0]}
                    />
                  ) : null}
                </span>
                <span className="swatch-meta">
                  <span className="swatch-name">
                    {brandNames.get(entry.b) ?? entry.b} {entry.s}
                  </span>
                  <span className="swatch-color">{entry.zh ?? entry.en}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
