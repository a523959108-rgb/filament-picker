import { useEffect } from "react";
import type { JSX } from "react";
import { similar, sourceBadge } from "../color";
import { purchaseHref } from "../purchase";
import type { WebCatalog, WebEntry } from "../types";

export function ColorDetail(props: {
  entry: WebEntry;
  catalog: WebCatalog;
  onClose: () => void;
  onCompare: (id: string) => void;
}): JSX.Element {
  const { entry, catalog, onClose } = props;
  const brandName = catalog.brands.find((brand) => brand.slug === entry.b)?.name ?? entry.b;
  const matches = similar(entry, catalog.entries);
  const entryName = entry.en ?? entry.zh ?? entry.id;
  const subName = entry.en !== null && entry.zh !== null ? entry.zh : null;
  const hexText = entry.hex.length > 0 ? entry.hex.join("、") : "无色值";
  const brandBySlug = new Map(catalog.brands.map((brand) => [brand.slug, brand.name]));
  const href = purchaseHref(entry.url);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="color-detail" role="dialog" aria-label="颜色详情">
        <div
          className={entry.hex[0] === undefined ? "color-detail-swatch swatch-empty" : "color-detail-swatch"}
          style={entry.hex[0] === undefined ? undefined : { backgroundColor: entry.hex[0] }}
          aria-label={entry.hex[0] ?? "无色值"}
        />
        <div className="color-detail-body">
          <header className="color-detail-header">
            <div>
              <p className="eyebrow">{brandName} · {entry.s}</p>
              <h2>{entryName}</h2>
              {subName !== null && <p className="color-detail-sub">{subName}{entry.code ? ` · ${entry.code}` : ""}</p>}
            </div>
            <button type="button" className="btn btn-ghost" onClick={onClose}>关闭</button>
          </header>

          <dl className="detail-meta">
            <div>
              <dt>色值</dt>
              <dd className="mono">{hexText}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd><span className="badge">{sourceBadge(entry.src, entry.conf)}</span></dd>
            </div>
            <div>
              <dt>材料</dt>
              <dd>{entry.m} · {entry.fam}</dd>
            </div>
          </dl>

          <div className="detail-actions">
            <button type="button" className="btn btn-primary" onClick={() => props.onCompare(entry.id)}>加入对比</button>
            {entry.url !== "" && (
              <p className="purchase">
                {href !== null ? (
                  <a href={href} target="_blank" rel="noreferrer">购买链接</a>
                ) : (
                  <span className="purchase-unavailable">暂未上架</span>
                )}
              </p>
            )}
          </div>

          {matches.length > 0 && (
            <section className="similar">
              <h3>相似色</h3>
              <ul>
                {matches.map(({ entry: match, delta }) => (
                  <li key={match.id}>
                    <button type="button" className="similar-item" onClick={() => props.onCompare(match.id)}>
                      <span
                        className={match.hex[0] === undefined ? "similar-dot swatch-empty" : "similar-dot"}
                        style={match.hex[0] === undefined ? undefined : { backgroundColor: match.hex[0] }}
                        aria-hidden="true"
                      />
                      <span className="similar-text">
                        {brandBySlug.get(match.b) ?? match.b} {match.s} {match.zh ?? match.en ?? match.id}（ΔE {delta.toFixed(1)}）
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </aside>
    </>
  );
}
