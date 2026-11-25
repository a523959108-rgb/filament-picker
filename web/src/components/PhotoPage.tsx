import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, JSX, MouseEvent } from "react";
import { loadCatalog } from "../catalog";
import {
  PHOTO_DEFAULT_K,
  PHOTO_SAMPLE_LONG_SIDE,
  downsampleRaster,
  drawSample,
  extractDominantColors,
  isHeicName,
  photoFileIssue,
  rgbAt,
  rgbToHex,
  type RgbaRaster,
} from "../photoExtract";
import { nearestSkus, singleIsClose, suggestStack, type PhotoSkuMatch, type StackSuggestion } from "../photoMatch";
import { stackHrefForColors } from "../stackPrefill";
import type { WebCatalog, WebEntry } from "../types";
import { SiteHeader } from "./SiteHeader";

export type PhotoColor = {
  hex: string;
  share: number | null;
  source: "auto" | "manual";
};

type Marker = { x: number; y: number };

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("decode"));
    image.src = url;
  });
}

function formatShare(share: number | null, source: PhotoColor["source"]): string {
  if (source === "manual" || share === null) return "手动";
  return `${Math.round(share * 100)}%`;
}

function MatchRow({ match }: { match: PhotoSkuMatch }): JSX.Element {
  return (
    <li className="pick">
      <span className="pick-dot" style={{ backgroundColor: match.hex }} aria-hidden="true" />
      <span className="pick-name">
        {match.brandName} {match.series} · {match.name}
        <span className="photo-meta">
          {match.entry.m}
          {match.price ? ` · ${match.price}` : ""}
        </span>
      </span>{" "}
      <span className="pick-delta mono">ΔE {match.delta.toFixed(2)}</span>{" "}
      <span className="badge">{match.label}</span>
      {match.isApprox && <span className="badge badge-warn"> 近似色</span>}{" "}
      <span className="pick-buy">
        {match.purchaseUrl !== null ? (
          <a href={match.purchaseUrl} target="_blank" rel="noopener noreferrer">
            购买
          </a>
        ) : (
          <span className="purchase-unavailable">暂无店铺链接</span>
        )}
      </span>
    </li>
  );
}

function StackOffer(props: {
  suggestion: StackSuggestion;
  bestDelta: number | null;
  href: string;
  allHref: string | null;
}): JSX.Element {
  const closer = props.bestDelta === null || props.suggestion.delta + 0.5 < props.bestDelta;
  const recipe = props.suggestion.parts
    .map((part) => `${part.name_zh} ${Math.round(part.weight * 100)}%`)
    .join(" · ");
  return (
    <section className="panel photo-stack" aria-label="叠色建议">
      <h3>叠色建议</h3>
      <p>
        {props.bestDelta === null
          ? "目录里没有可比较的单色。"
          : `最近的单支耗材 ΔE ${props.bestDelta.toFixed(2)}，超过 ${10}，单色不够接近。`}
        {closer
          ? ` 按现有 RYBW 托盘做线性混合，估算可以到 ΔE ${props.suggestion.delta.toFixed(2)}。`
          : ` 仍可改用四色叠色去逼近。线性混合估算 ΔE ${props.suggestion.delta.toFixed(2)}，不一定比单色更好。`}
        这不是本机叠色引擎的 LUT 结果，正式效果以引擎为准。
      </p>
      <div className="photo-stack-recipe">
        <span className="plan-target-swatch" style={{ backgroundColor: props.suggestion.mixedHex }} aria-hidden="true" />
        <span>
          {recipe || "四色托盘"}
          <span className="photo-meta mono">估算 {props.suggestion.mixedHex}</span>
        </span>
      </div>
      <ul className="photo-stack-parts">
        {props.suggestion.parts.map((part) => (
          <li key={part.slot}>
            <span className="pick-dot" style={{ backgroundColor: part.hex }} aria-hidden="true" />
            {part.slot} {part.name_zh}
            <span className="photo-meta">{part.catalog_id}</span>
          </li>
        ))}
      </ul>
      <div className="photo-stack-actions">
        <a className="btn btn-primary" href={props.href}>
          用这个颜色打开叠色
        </a>
        {props.allHref !== null && (
          <a className="btn btn-ghost" href={props.allHref}>
            带入全部主色
          </a>
        )}
      </div>
    </section>
  );
}

export function PhotoResults(props: {
  colors: PhotoColor[];
  entries: WebEntry[];
  brands: { slug: string; name: string }[];
  hostname?: string;
  selectedHex?: string | null;
  onRemoveColor?: (hex: string) => void;
}): JSX.Element {
  const hostname = props.hostname ?? window.location.hostname;
  const [active, setActive] = useState<string | null>(props.selectedHex ?? props.colors[0]?.hex ?? null);

  useEffect(() => {
    if (props.selectedHex && props.colors.some((color) => color.hex === props.selectedHex)) {
      setActive(props.selectedHex);
      return;
    }
    setActive((current) =>
      current !== null && props.colors.some((color) => color.hex === current)
        ? current
        : (props.colors[0]?.hex ?? null),
    );
  }, [props.colors, props.selectedHex]);

  const color = props.colors.find((item) => item.hex === active) ?? null;
  const matches = useMemo(
    () => (color === null ? [] : nearestSkus(color.hex, props.entries, props.brands, 4)),
    [color, props.entries, props.brands],
  );
  const suggestion = useMemo(() => (color === null ? null : suggestStack(color.hex)), [color]);
  const close = singleIsClose(matches);
  const allHref =
    props.colors.length > 1 ? stackHrefForColors(hostname, props.colors.map((item) => item.hex)) : null;

  if (props.colors.length === 0) {
    return (
      <div className="panel empty-state">
        <p>上传照片后，主色和最接近的耗材会显示在这里。</p>
      </div>
    );
  }

  return (
    <div className="photo-results">
      <div className="photo-chips" role="list" aria-label="提取的颜色">
        {props.colors.map((item) => {
          const removable = item.source === "manual" && props.onRemoveColor !== undefined;
          return (
            <div key={`${item.source}-${item.hex}`} className="photo-chip-wrap" role="listitem">
              <button
                type="button"
                className={item.hex === active ? "photo-chip is-selected" : "photo-chip"}
                aria-pressed={item.hex === active}
                onClick={() => setActive(item.hex)}
              >
                <span className="photo-chip-swatch" style={{ backgroundColor: item.hex }} />
                <span className="mono">{item.hex}</span>
                <span>{formatShare(item.share, item.source)}</span>
              </button>
              {removable ? (
                <button
                  type="button"
                  className="photo-chip-remove"
                  aria-label={`移除 ${item.hex}`}
                  onClick={() => props.onRemoveColor?.(item.hex)}
                >
                  ×
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
      {color !== null && (
        <article className="panel plan-target">
          <div className="plan-target-heading">
            <span className="plan-target-swatch" style={{ backgroundColor: color.hex }} aria-label={color.hex} />
            <span className="mono">{color.hex}</span>
            <span className="plan-share">{formatShare(color.share, color.source)}</span>
          </div>
          <p className="photo-note">按 CIEDE2000（ΔE）在色卡目录里找最近的单色耗材。</p>
          {matches.length === 0 ? (
            <p className="empty-state">目录里没有可比较的单色。</p>
          ) : (
            <ul className="pick-list">
              {matches.map((match) => (
                <MatchRow key={match.entry.id} match={match} />
              ))}
            </ul>
          )}
        </article>
      )}
      {!close && suggestion !== null && color !== null && (
        <StackOffer
          suggestion={suggestion}
          bestDelta={matches[0]?.delta ?? null}
          href={stackHrefForColors(hostname, [color.hex])}
          allHref={allHref}
        />
      )}
    </div>
  );
}

export function PhotoPage(): JSX.Element {
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileLabel, setFileLabel] = useState("尚未选择");
  const [preview, setPreview] = useState<string | null>(null);
  const [raster, setRaster] = useState<RgbaRaster | null>(null);
  const [k, setK] = useState(PHOTO_DEFAULT_K);
  const [colors, setColors] = useState<PhotoColor[]>([]);
  const [marker, setMarker] = useState<Marker | null>(null);
  const [selectedHex, setSelectedHex] = useState<string | null>(null);

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

  useEffect(() => {
    return () => {
      if (preview !== null) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  useEffect(() => {
    if (raster === null) return;
    const down = downsampleRaster(raster, 80);
    const extracted = extractDominantColors(down.pixels, down.width, down.height, { k, seed: 0 });
    setColors((current) => {
      const manuals = current.filter((color) => color.source === "manual");
      const auto = extracted.map((color) => ({ hex: color.hex, share: color.share, source: "auto" as const }));
      const autoHex = new Set(auto.map((color) => color.hex));
      return [...manuals.filter((color) => !autoHex.has(color.hex)), ...auto];
    });
  }, [raster, k]);

  const readFile = async (file: File) => {
    const issue = photoFileIssue(file);
    if (issue !== null) {
      setFileError(issue);
      return;
    }
    const url = URL.createObjectURL(file);
    try {
      const image = await loadImage(url);
      const sample = drawSample(image, image.naturalWidth, image.naturalHeight, PHOTO_SAMPLE_LONG_SIDE);
      if (sample === null) throw new Error("canvas");
      setPreview((current) => {
        if (current !== null) URL.revokeObjectURL(current);
        return url;
      });
      setRaster(sample);
      setMarker(null);
      setSelectedHex(null);
      setColors([]);
      setFileLabel(file.name);
      setFileError(null);
    } catch {
      URL.revokeObjectURL(url);
      setFileError(
        isHeicName(file)
          ? "浏览器无法解码这张 HEIC。请在相册里导出为 JPG 或 PNG 后再试。"
          : "这张图无法解码。请改用 JPG、PNG 或 WebP。",
      );
    }
  };

  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void readFile(file);
  };

  const onSample = async () => {
    setFileError(null);
    try {
      const response = await fetch("./photo-sample.png");
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      await readFile(new File([blob], "photo-sample.png", { type: "image/png" }));
    } catch {
      setFileError("示例图加载失败。");
    }
  };

  const onPick = (event: MouseEvent<HTMLButtonElement>) => {
    if (raster === null) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    if (x < 0 || y < 0 || x > 1 || y > 1) return;
    const px = Math.min(raster.width - 1, Math.max(0, Math.floor(x * raster.width)));
    const py = Math.min(raster.height - 1, Math.max(0, Math.floor(y * raster.height)));
    const rgb = rgbAt(raster, px, py);
    if (rgb === null) return;
    const hex = rgbToHex(rgb);
    setMarker({ x, y });
    setSelectedHex(hex);
    setColors((current) => {
      if (current.some((color) => color.hex === hex)) return current;
      return [{ hex, share: null, source: "manual" }, ...current];
    });
  };

  return (
    <section className="photo-page">
      <SiteHeader
        page="photo"
        title="拍照找耗材"
        subtitle="上传实物或模型照片，提取主色，匹配最接近的可买耗材"
      />

      <div className="photo-layout">
        <div className="panel photo-form">
          <div className="field">
            <span className="field-label">照片</span>
            <div className="photo-file-row">
              <label className="btn btn-ghost photo-file-btn">
                选择照片
                <input
                  className="photo-file"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.jpg,.jpeg,.png,.webp,.heic,.heif"
                  aria-label="选择照片"
                  onChange={onFile}
                />
              </label>
              <span className="dropzone-hint">{fileLabel}</span>
            </div>
          </div>
          <p className="dropzone-hint">
            支持 JPG、PNG、WebP，HEIC 视浏览器而定。上限 10MB。照片只在这台设备上取色，不会上传，也不会保存到服务器。
          </p>
          <div className="photo-tools">
            <button type="button" className="btn btn-ghost" onClick={() => void onSample()}>
              用示例照片试试
            </button>
            <label className="field photo-k">
              <span className="field-label">主色数量</span>
              <select aria-label="主色数量" value={k} onChange={(event) => setK(Number(event.target.value))}>
                {[3, 4, 5, 6].map((count) => (
                  <option key={count} value={count}>
                    {count}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {fileError !== null && (
            <p className="plan-error" role="alert">
              {fileError}
            </p>
          )}
          {preview !== null && (
            <div className="photo-stage-wrap">
              <button type="button" className="photo-stage" aria-label="点击图片取色" onClick={onPick}>
                <img src={preview} alt="待取色的照片" />
                {marker !== null && (
                  <span
                    className="photo-marker"
                    style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
                  />
                )}
              </button>
              <p className="dropzone-hint">点一下画面上的颜色，可以手动指定要匹配的色。</p>
            </div>
          )}
        </div>

        {loadError && <p className="panel empty-state">目录加载失败</p>}
        {!loadError && catalog === null && <p className="panel empty-state">目录加载中…</p>}
        {!loadError && catalog !== null && (
          <PhotoResults
            colors={colors}
            entries={catalog.entries}
            brands={catalog.brands}
            selectedHex={selectedHex}
            onRemoveColor={(hex) =>
              setColors((current) =>
                current.filter((color) => !(color.source === "manual" && color.hex === hex)),
              )
            }
          />
        )}
      </div>
    </section>
  );
}
