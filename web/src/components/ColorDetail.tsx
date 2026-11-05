import type { JSX } from "react";
import { similar, sourceBadge } from "../color";
import type { WebCatalog, WebEntry } from "../types";

export function ColorDetail(props: {
  entry: WebEntry;
  catalog: WebCatalog;
  onClose: () => void;
  onCompare: (id: string) => void;
}): JSX.Element {
  const { entry, catalog } = props;
  const brandName = catalog.brands.find((brand) => brand.slug === entry.b)?.name ?? entry.b;
  const matches = similar(entry, catalog.entries);
  const entryName = entry.en ?? entry.zh ?? entry.id;
  const hexText = entry.hex.length > 0 ? entry.hex.join("、") : "无色值";
  const brandBySlug = new Map(catalog.brands.map((brand) => [brand.slug, brand.name]));

  return (
    <aside className="color-detail" role="dialog" aria-label="颜色详情">
      <div>
        <h2>{entryName}</h2>
        <button type="button" onClick={props.onClose}>关闭</button>
      </div>
      <div
        className="color-detail-swatch"
        style={entry.hex[0] === undefined ? undefined : { backgroundColor: entry.hex[0] }}
        aria-label={entry.hex[0] ?? "无色值"}
      />
      <p>{brandName} · {entry.s}</p>
      <p>{hexText}</p>
      <p>{sourceBadge(entry.src, entry.conf)}</p>
      {entry.url && (
        <p>
          <a href={entry.url} target="_blank" rel="noreferrer">购买链接</a>
          {entry.price && <span>（{entry.price}）</span>}
        </p>
      )}
      <button type="button" onClick={() => props.onCompare(entry.id)}>加入对比</button>
      {matches.length > 0 && (
        <section>
          <h3>相似色</h3>
          <ul>
            {matches.map(({ entry: match, delta }) => (
              <li key={match.id}>
                <button type="button" onClick={() => props.onCompare(match.id)}>
                  {brandBySlug.get(match.b) ?? match.b} {match.s} {match.zh ?? match.en ?? match.id}（ΔE {delta.toFixed(1)}）
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
