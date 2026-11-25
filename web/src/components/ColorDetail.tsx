import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import { fetchInStock } from "../api";
import { similar, sourceBadge, swatchBackgroundStyle } from "../color";
import { SIMILAR_EXCLUDE_EFFECTS } from "../config";
import { purchaseHref } from "../purchase";
import type { WebCatalog, WebEntry } from "../types";
import { CostCalculator } from "./CostCalculator";
import { PrintParams } from "./PrintParams";

const EXCLUDE_EFFECTS = new Set<string>(SIMILAR_EXCLUDE_EFFECTS);

export function ColorDetail(props: {
  entry: WebEntry;
  catalog: WebCatalog;
  onClose: () => void;
  onCompare: (id: string) => void;
  onSelect?: (id: string) => void;
}): JSX.Element {
  const { entry, catalog, onClose } = props;
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const brandName = catalog.brands.find((brand) => brand.slug === entry.b)?.name ?? entry.b;
  const matches = similar(entry, catalog.entries);
  const entryName = entry.en ?? entry.zh ?? entry.id;
  const subName = entry.en !== null && entry.zh !== null ? entry.zh : null;
  const hexText = entry.hex.length > 0 ? entry.hex.join("、") : "无色值";
  const brandBySlug = new Map(catalog.brands.map((brand) => [brand.slug, brand.name]));
  const [inStock, setInStock] = useState(false);
  const href = purchaseHref(entry.url);
  const altHref = entry.alt_url ? purchaseHref(entry.alt_url) : null;
  const specialNote = entry.eff.some((effect) => EXCLUDE_EFFECTS.has(effect))
    ? "该耗材为特殊效果料，色值仅供参考，不做跨品牌相似推荐。"
    : null;

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  useEffect(() => {
    if (panelRef.current !== null) {
      panelRef.current.scrollTop = 0;
    }
  }, [entry.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let active = true;
    setInStock(false);
    fetchInStock(entry.id)
      .then((value) => {
        if (active) setInStock(value);
      })
      .catch(() => {
        if (active) setInStock(false);
      });
    return () => {
      active = false;
    };
  }, [entry.id]);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside ref={panelRef} className="color-detail" role="dialog" aria-modal="true" aria-label="颜色详情">
        <div
          className={[
            "color-detail-swatch",
            entry.img ? "swatch-has-img" : "",
            !entry.img && entry.hex[0] === undefined ? "swatch-empty" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={!entry.img ? swatchBackgroundStyle(entry.hex) : undefined}
          aria-label={entry.hex[0] ?? (entry.img ? "SKU 图片" : "无色值")}
        >
          {entry.img ? (
            <img className="swatch-img" src={entry.img} alt="" loading="lazy" decoding="async" />
          ) : null}
          {entry.img && entry.hex[0] !== undefined ? (
            <span
              className="swatch-hex-dot"
              style={swatchBackgroundStyle(entry.hex)}
              title={entry.hex.join(" / ")}
            />
          ) : null}
        </div>
        <div className="color-detail-body">
          <header className="color-detail-header">
            <div>
              <p className="eyebrow">{brandName} · {entry.s}</p>
              <h2>
                {entryName}
                {inStock ? <span className="badge badge-stock">库存有</span> : null}
              </h2>
              {subName !== null && <p className="color-detail-sub">{subName}{entry.code ? ` · ${entry.code}` : ""}</p>}
            </div>
            <button ref={closeRef} type="button" className="btn btn-ghost" onClick={onClose}>关闭</button>
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
              <dd>{entry.m} · {entry.fam}{entry.eff.length > 0 ? ` · ${entry.eff.join("/")}` : ""}</dd>
            </div>
          </dl>

          {specialNote !== null && <p className="similar-note">{specialNote}</p>}

          <PrintParams print={entry.print} />

          <div className="detail-actions">
            <button type="button" className="btn btn-primary" onClick={() => props.onCompare(entry.id)}>加入对比</button>
            {entry.url !== "" && (
              <p className="purchase">
                {href !== null ? (
                  <a href={href} target="_blank" rel="noreferrer">购买链接</a>
                ) : (
                  <span className="purchase-unavailable">暂未上架</span>
                )}
                {altHref !== null && (
                  <a className="purchase-alt" href={altHref} target="_blank" rel="noreferrer">原链接</a>
                )}
              </p>
            )}
          </div>

          {matches.length > 0 && (
            <section className="similar">
              <h3>相似色</h3>
              <ul>
                {matches.map(({ entry: match, delta, isApprox }) => (
                  <li key={match.id} className="similar-row">
                    <button type="button" className="similar-item" onClick={() => props.onSelect?.(match.id)}>
                      <span
                        className={match.hex[0] === undefined ? "similar-dot swatch-empty" : "similar-dot"}
                        style={swatchBackgroundStyle(match.hex)}
                        aria-hidden="true"
                      />
                      <span className="similar-text">
                        {brandBySlug.get(match.b) ?? match.b} {match.s} {match.zh ?? match.en ?? match.id}
                        （ΔE {delta.toFixed(1)}）
                        {isApprox ? <span className="badge badge-warn"> 近似色</span> : null}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost similar-compare"
                      onClick={() => props.onCompare(match.id)}
                    >
                      加入对比
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <CostCalculator />
        </div>
      </aside>
    </>
  );
}
