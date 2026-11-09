import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, CSSProperties, FormEvent, JSX, PointerEvent as ReactPointerEvent } from "react";
import { cardSrc, postPlan } from "../api";
import { purchaseHref } from "../purchase";
import { pointInBox, regionFromDrag, type SampleRegion } from "../regions";
import type { PlanResult } from "../types";

function regionStyle(region: SampleRegion, natural: { w: number; h: number } | null): CSSProperties {
  if (region.w !== undefined && region.h !== undefined) {
    return {
      left: `${region.x * 100}%`,
      top: `${region.y * 100}%`,
      width: `${region.w * 100}%`,
      height: `${region.h * 100}%`,
    };
  }
  const radius = region.r ?? 0.04;
  const minOverW = natural === null ? 1 : Math.min(natural.w, natural.h) / natural.w;
  const minOverH = natural === null ? 1 : Math.min(natural.w, natural.h) / natural.h;
  const width = radius * minOverW * 2;
  const height = radius * minOverH * 2;
  return {
    left: `${(region.x - width / 2) * 100}%`,
    top: `${(region.y - height / 2) * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  };
}

export function PlanPage(props: { post?: typeof postPlan }): JSX.Element {
  const post = props.post ?? postPlan;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [note, setNote] = useState("");
  const [regions, setRegions] = useState<SampleRegion[]>([]);
  const [draft, setDraft] = useState<SampleRegion | null>(null);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const fileRef = useRef<File | null>(null);
  const noteRef = useRef("");
  const regionsRef = useRef<SampleRegion[]>([]);
  fileRef.current = file;
  noteRef.current = note;

  useEffect(() => {
    if (file === null) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const run = async (nextRegions: SampleRegion[]) => {
    const current = fileRef.current;
    if (current === null) {
      setError("请先选择图片");
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const next =
        nextRegions.length > 0
          ? await post(current, noteRef.current, { regions: nextRegions })
          : await post(current, noteRef.current);
      setResult(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  };

  const commitRegions = (next: SampleRegion[]) => {
    regionsRef.current = next;
    setRegions(next);
    if (fileRef.current !== null) {
      void run(next);
    }
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    regionsRef.current = [];
    setRegions([]);
    setDraft(null);
    setNatural(null);
    setFile(event.target.files?.[0] ?? null);
    setError(null);
    setResult(null);
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run(regionsRef.current);
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (submitting) return;
    event.preventDefault();
    const box = event.currentTarget.getBoundingClientRect();
    dragStart.current = pointInBox(event.clientX, event.clientY, box);
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // jsdom 没有指针捕获时，pointerup 仍落在同一元素上。
    }
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStart.current === null) return;
    const box = event.currentTarget.getBoundingClientRect();
    const end = pointInBox(event.clientX, event.clientY, box);
    setDraft(regionFromDrag(dragStart.current, end, box.width, box.height));
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStart.current === null) return;
    const box = event.currentTarget.getBoundingClientRect();
    const end = pointInBox(event.clientX, event.clientY, box);
    const region = regionFromDrag(dragStart.current, end, box.width, box.height);
    dragStart.current = null;
    setDraft(null);
    commitRegions([...regionsRef.current, region]);
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
          <a href="#/stack" className="nav-link">叠色</a>
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
          {preview !== null && (
            <div className="region-editor">
              <p className="dropzone-hint">在图上拖红框，或点一下取一块颜色。不选则用整张图。</p>
              <div
                className="region-stage"
                role="application"
                aria-label="取色区域"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
              >
                <img
                  src={preview}
                  alt="待配色图片"
                  draggable={false}
                  onLoad={(event) =>
                    setNatural({
                      w: event.currentTarget.naturalWidth,
                      h: event.currentTarget.naturalHeight,
                    })
                  }
                />
                {regions.map((region, index) => (
                  <span
                    key={`${region.x}-${region.y}-${region.w ?? "p"}-${index}`}
                    className={region.w === undefined ? "region-mark region-point" : "region-mark"}
                    style={regionStyle(region, natural)}
                  />
                ))}
                {draft !== null && (
                  <span
                    className={draft.w === undefined ? "region-mark region-point" : "region-mark"}
                    style={regionStyle(draft, natural)}
                  />
                )}
              </div>
              {regions.length > 0 && (
                <div className="region-tools">
                  <span>已选 {regions.length} 处</span>
                  <button type="button" onClick={() => commitRegions([])}>
                    清除选区
                  </button>
                </div>
              )}
            </div>
          )}
          <label className="field">
            <span className="field-label">备注</span>
            <textarea
              placeholder="例：4 色，AMS 一台，只要拓竹 PLA"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "配色中…" : regions.length > 0 ? "按选区重算" : "开始配色"}
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
