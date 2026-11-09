import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "../catalog";
import {
  copyText,
  listGoodsOffers,
  spoolYuanAsPricePerKg,
  summarizeMarketPrices,
  type GoodsOfferRow,
} from "../marketPrice";
import type { WebCatalog } from "../types";
import { CostCalculator } from "./CostCalculator";

const PREVIEW_LIMIT = 12;

export function CostPage(): JSX.Element {
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [appliedPricePerKg, setAppliedPricePerKg] = useState<number | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let active = true;
    loadCatalog()
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const rows = useMemo(
    () => (catalog === null ? [] : listGoodsOffers(catalog.entries)),
    [catalog],
  );
  const summary = useMemo(() => summarizeMarketPrices(rows), [rows]);
  const visibleRows = showAll ? rows : rows.slice(0, PREVIEW_LIMIT);

  const onCopy = async (row: GoodsOfferRow) => {
    const ok = await copyText(row.url);
    setCopyStatus(ok ? `已复制：${row.name}` : "复制失败，请长按链接手动复制");
  };

  const onApply = (row: GoodsOfferRow) => {
    if (row.cnyYuan == null) {
      setCopyStatus("该条暂无 CNY 报价，未改计算器单价");
      return;
    }
    setAppliedPricePerKg(spoolYuanAsPricePerKg(row.cnyYuan));
    setCopyStatus(`已用 ${row.cnyYuan} 元/千克（按 1kg 卷卡价）`);
  };

  const onApplyMedian = () => {
    if (summary.medianCny == null) {
      setCopyStatus("尚无可用 CNY 价区间");
      return;
    }
    setAppliedPricePerKg(spoolYuanAsPricePerKg(summary.medianCny));
    setCopyStatus(`已用中位卡价 ${summary.medianCny} 元/千克`);
  };

  return (
    <section className="cost-page">
      <header className="topbar">
        <div className="topbar-title">
          <h1>打印成本</h1>
          <p className="topbar-sub">按用料和电费估算一次打印要花多少钱；可参考拼多多真链卡价</p>
        </div>
        <nav className="topbar-nav" aria-label="页面导航">
          <a href="#/" className="nav-link">色卡浏览</a>
          <a href="#/plan" className="nav-link">图片配色</a>
          <a href="#/stack" className="nav-link">叠色</a>
        </nav>
      </header>
      <div className="panel cost-panel">
        <CostCalculator appliedPricePerKg={appliedPricePerKg} />
      </div>
      <div className="panel cost-market" aria-label="真链单价">
        <h2>真链单价</h2>
        {loadError && <p className="empty-state">目录加载失败，无法展示真链价</p>}
        {!loadError && catalog === null && <p className="empty-state">正在读取目录里的拼多多真链…</p>}
        {!loadError && catalog !== null && (
          <>
            <p className="cost-formula">
              共 {summary.goodsCount} 条 PDD 商品真链；有 price_text {summary.withPriceText} 条；
              可解析 CNY 卡价 {summary.cnyParsable} 条
              {summary.minCny != null && summary.maxCny != null
                ? `；区间 ${summary.minCny}–${summary.maxCny} 元（中位 ${summary.medianCny}）`
                : ""}
              。
            </p>
            <p className="cost-gap" role="note">
              {summary.gapNote}
            </p>
            <div className="cost-market-actions">
              <button type="button" className="btn btn-ghost" onClick={onApplyMedian} disabled={summary.medianCny == null}>
                用中位卡价填计算器
              </button>
            </div>
            {copyStatus && (
              <p className="toast" role="status">
                {copyStatus}
              </p>
            )}
            <ul className="cost-offer-list">
              {visibleRows.map((row) => (
                <li key={row.id} className="cost-offer-row">
                  <div className="cost-offer-main">
                    <span className="cost-offer-name">
                      {row.name}
                      <span className="cost-offer-meta">
                        {" "}
                        · {row.brandSlug} · {row.series}
                      </span>
                    </span>
                    <span className="cost-offer-price">
                      {row.priceText && row.priceText.trim() !== "" ? row.priceText : "暂无报价"}
                    </span>
                  </div>
                  <div className="cost-offer-actions">
                    <button type="button" className="btn btn-ghost" onClick={() => void onCopy(row)}>
                      复制购买链接
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => onApply(row)}
                      disabled={row.cnyYuan == null}
                    >
                      用到计算器
                    </button>
                    <a className="nav-link" href={row.url} target="_blank" rel="noreferrer">
                      打开
                    </a>
                  </div>
                </li>
              ))}
            </ul>
            {rows.length > PREVIEW_LIMIT && (
              <button type="button" className="btn btn-ghost" onClick={() => setShowAll((value) => !value)}>
                {showAll ? "收起列表" : `显示全部 ${rows.length} 条`}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}
