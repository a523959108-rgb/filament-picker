import { useState } from "react";
import type { ChangeEvent, FormEvent, JSX } from "react";
import { cardSrc, postPlan } from "../api";
import { purchaseHref } from "../purchase";
import type { PlanResult } from "../types";

export function PlanPage(props: { post?: typeof postPlan }): JSX.Element {
  const post = props.post ?? postPlan;
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setError(null);
    setResult(null);
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (file === null) {
      setError("请先选择图片");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await post(file, note));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  const imageSource = result === null ? null : cardSrc(result);

  return (
    <section className="plan-page">
      <header className="topbar">
        <div className="topbar-title">
          <h1>图片配色（T24）</h1>
          <p className="topbar-sub">上传一张图，按主色匹配可买到的耗材</p>
        </div>
        <nav className="topbar-nav" aria-label="页面导航">
          <a href="#/" className="nav-link">色卡浏览</a>
          <a href="#/cost" className="nav-link">打印成本</a>
        </nav>
      </header>

      <div className="plan-layout">
        <form className="panel plan-form" onSubmit={onSubmit}>
          <div className="dropzone">
            <label className="field">
              <span className="field-label">图片</span>
              <input type="file" accept="image/*" onChange={onFileChange} />
            </label>
            <p className="dropzone-hint">{file === null ? "选择 PNG / JPG 图片" : file.name}</p>
          </div>
          <label className="field">
            <span className="field-label">备注</span>
            <textarea
              placeholder="例：4 色，AMS 一台，只要拓竹 PLA"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "配色中…" : "开始配色"}
          </button>
          {error !== null && <p className="plan-error">{error}</p>}
          {result?.status === "error" && <p className="plan-error">{result.error?.message_zh}</p>}
        </form>

        {result?.status === "ok" ? (
          <section className="plan-result">
            <div className="plan-result-head">
              <h2>配色方案（{result.palette.length} 色）</h2>
              <p className="plan-slots">需要 {result.slots_used} 个料槽</p>
            </div>
            {result.palette.map((target) => {
              const match = result.matches.find((item) => item.target_index === target.index);
              return (
                <article key={target.index} className="panel plan-target">
                  <div className="plan-target-heading">
                    <span
                      className="plan-target-swatch"
                      style={{ backgroundColor: target.hex }}
                      aria-label={target.hex}
                    />
                    <span className="mono">{target.hex}</span>
                    <span className="plan-share">{Math.round(target.share * 100)}%</span>
                  </div>
                  {match !== undefined && (
                    <ul className="pick-list">
                      {match.picks.map((pick) => {
                        const href = purchaseHref(pick.url);
                        const altHref = pick.alt_url ? purchaseHref(pick.alt_url) : null;
                        return (
                          <li key={pick.id} className="pick">
                            <span
                              className="pick-dot"
                              style={{ backgroundColor: pick.hex }}
                              aria-hidden="true"
                            />
                            <span className="pick-name">
                              {pick.brand_name} {pick.series_name} · {pick.name_display}
                            </span>{" "}
                            <span className="pick-delta mono">ΔE {pick.delta_e.toFixed(1)}</span>{" "}
                            <span className="badge">{pick.label}</span>
                            {pick.is_approx && <span className="badge badge-warn"> 近似色</span>}
                            {pick.stock?.in_stock === true && (
                              <span className="badge badge-stock"> 库存有</span>
                            )}{" "}
                            <span className="pick-buy">
                              {href !== null ? (
                                <a href={href}>购买</a>
                              ) : (
                                <span className="purchase-unavailable">暂未上架</span>
                              )}
                              {altHref !== null && <a href={altHref}>原链接</a>}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </article>
              );
            })}
            {result.single_series_option !== null && (
              <p className="plan-note">
                同系列方案：{result.single_series_option.brand_name} {result.single_series_option.series_name}（最大 ΔE {result.single_series_option.max_delta_e.toFixed(1)}）
              </p>
            )}
            {imageSource !== null && <img className="plan-card" src={imageSource} alt="配色卡" />}
          </section>
        ) : (
          <div className="panel empty-state plan-placeholder">
            <p>配色结果会显示在这里</p>
          </div>
        )}
      </div>
    </section>
  );
}
