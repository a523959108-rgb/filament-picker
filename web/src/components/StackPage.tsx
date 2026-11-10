import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, JSX } from "react";
import { loadCatalog } from "../catalog";
import { SOURCE_URL } from "../config";
import { copyText } from "../marketPrice";
import { moveSlot } from "../stackSlots";
import {
  applyStackResult,
  parseStackResultText,
  type ImportedStackView,
} from "../stackImport";
import {
  buildJobPackageZip,
  buildStackJob,
  loadTrayMap,
  triggerBlobDownload,
  type FourColorTrayMap,
  type StackLutMode,
  type TraySlot,
} from "../stackJob";
import {
  SMOKE_INPUT_URL,
  SMOKE_MODEL_3MF_URL,
  SMOKE_PREVIEW_URL,
  SMOKE_RYBW_SLOTS,
  recommendSlots,
  toStackResult,
  type SlotRecommendation,
} from "../stackRecommend";
import type { WebCatalog } from "../types";
import { StackBed } from "./StackBed";
import Button from "../vendor/lumina/components/ui/Button";
import DisclosureChevron from "../vendor/lumina/components/ui/DisclosureChevron";
import ImageUpload from "../vendor/lumina/components/ui/ImageUpload";
import {
  cardClass,
  settingsGroupHeadingClass,
  workstationInputClass,
} from "../vendor/lumina/components/ui/panelPrimitives";
import "../vendor/lumina/lumina-theme.css";

const DEFAULT_SIZE_MM = 100;

const BED_PRESETS = [
  { id: "256", label: "256 × 256 mm", width: 256, height: 256 },
  { id: "350", label: "350 × 320 mm", width: 350, height: 320 },
  { id: "180", label: "180 × 180 mm", width: 180, height: 180 },
] as const;

type PreviewView = "bed" | "original" | "stacked" | "split";

function formatDelta(delta: number): string {
  return delta.toFixed(2);
}

function tierLabel(tier: SlotRecommendation["match_tier"]): string {
  switch (tier) {
    case "preferred_series":
      return "优选系列";
    case "same_brand_fallback":
      return "同品牌回退";
    case "cross_brand_fallback":
      return "跨品牌备选";
    default:
      return tier;
  }
}

export function StackPage(): JSX.Element {
  const [trayMap, setTrayMap] = useState<FourColorTrayMap | null>(null);
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [catalogError, setCatalogError] = useState(false);
  const [mode, setMode] = useState<StackLutMode>("RYBW");
  const [widthMm, setWidthMm] = useState(DEFAULT_SIZE_MM);
  const [heightMm, setHeightMm] = useState(DEFAULT_SIZE_MM);
  const [layerHeightMm, setLayerHeightMm] = useState(0.08);
  const [bedId, setBedId] = useState<(typeof BED_PRESETS)[number]["id"]>("256");
  const [image, setImage] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importText, setImportText] = useState("");
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [imported, setImported] = useState<ImportedStackView | null>(null);
  const [slotOrder, setSlotOrder] = useState<string[] | null>(null);
  const [view, setView] = useState<PreviewView>("bed");
  const [previewOn, setPreviewOn] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const dragFrom = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    loadTrayMap()
      .then((value) => {
        if (active) setTrayMap(value);
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    loadCatalog()
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setCatalogError(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const palette = trayMap?.palettes[mode] ?? null;
  const previewUrl = useMemo(() => (image === null ? null : URL.createObjectURL(image)), [image]);
  const bed = BED_PRESETS.find((item) => item.id === bedId) ?? BED_PRESETS[0];

  const orderedSlots: TraySlot[] = useMemo(() => {
    const slots = palette?.slots ?? [];
    if (slotOrder === null) return slots;
    const byLetter = new Map(slots.map((slot) => [slot.slot, slot]));
    const ordered = slotOrder
      .map((letter) => byLetter.get(letter))
      .filter((slot): slot is TraySlot => slot !== undefined);
    const rest = slots.filter((slot) => !slotOrder.includes(slot.slot));
    return [...ordered, ...rest];
  }, [palette, slotOrder]);

  const smokeRecs: SlotRecommendation[] = useMemo(() => {
    if (catalog === null) return [];
    return recommendSlots(SMOKE_RYBW_SLOTS, catalog.entries ?? [], {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
  }, [catalog]);

  const activeRecs = imported?.slots ?? smokeRecs;
  const activeLut = imported?.lutMode ?? mode;
  const usingFixture = previewOn && image === null && imported === null;
  const originalSrc = previewOn ? (previewUrl ?? (imported === null ? SMOKE_INPUT_URL : null)) : null;
  const stackedSrc = previewOn
    ? (imported?.previewUrl ?? (image === null && imported === null ? SMOKE_PREVIEW_URL : null))
    : null;
  const activeModelUrl = previewOn || imported !== null ? (imported?.modelUrl ?? SMOKE_MODEL_3MF_URL) : null;
  const activeModelName = imported?.modelDownloadName ?? "smoke_rybw_sample_logo.3mf";
  const bedArtwork = view === "bed" ? (stackedSrc ?? originalSrc) : null;

  useEffect(() => {
    return () => {
      if (previewUrl !== null) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const applyImportText = useCallback(
    (text: string, sourceLabel: string) => {
      if (catalog === null) {
        setImportStatus("目录尚未加载，稍后再导入");
        return;
      }
      const parsed = parseStackResultText(text);
      if (!parsed.ok) {
        setImportStatus(parsed.message);
        return;
      }
      const next = applyStackResult(parsed.result, catalog.entries ?? [], sourceLabel);
      setImported(next);
      setMode(next.lutMode);
      setSlotOrder(null);
      setPreviewOn(true);
      setView(next.previewUrl ? "split" : "stacked");
      setImportStatus(
        `已导入并刷新：${sourceLabel} · ${next.lutMode} · ${next.slots.length} 槽（推荐按当前目录重算）`,
      );
    },
    [catalog],
  );

  const onImportFile = async (file: File) => {
    try {
      const text = await file.text();
      setImportText(text);
      applyImportText(text, file.name);
    } catch (reason) {
      setImportStatus(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const onImportInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void onImportFile(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files?.[0];
    if (file) {
      void onImportFile(file);
      return;
    }
    const text = event.dataTransfer.getData("text/plain");
    if (text.trim()) {
      setImportText(text);
      applyImportText(text, "拖入文本");
    }
  };

  const onPreview = () => {
    setPreviewOn(true);
    const hasOriginal = image !== null || imported === null;
    const hasStacked = imported?.previewUrl != null || (image === null && imported === null);
    if (hasOriginal && hasStacked) setView("split");
    else if (hasStacked) setView("stacked");
    else setView("original");
  };

  const onDownload = async () => {
    if (palette === null) {
      setStatus("托盘映射未加载");
      return;
    }
    if (!(widthMm > 0) || !(heightMm > 0)) {
      setStatus("宽高 mm 须为正数");
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const job = buildStackJob({
        mode,
        palette: { ...palette, slots: orderedSlots },
        widthMm,
        heightMm,
        imageFilename: image?.name ?? null,
      });
      const zip = await buildJobPackageZip(job, image);
      const stamp = job.created_at.replace(/[:]/g, "").slice(0, 15);
      triggerBlobDownload(zip, `lumina-stack-job-${mode}-${stamp}.zip`);
      setStatus(image ? "已下载任务包（job.json + 原图）" : "已下载任务包（仅 job.json；可稍后在本机补图）");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const onCopyBuy = async (rec: SlotRecommendation) => {
    if (rec.purchase_url === null) {
      setCopyStatus("该色暂无购买链接");
      return;
    }
    const ok = await copyText(rec.purchase_url);
    const name = rec.entry.zh || rec.entry.en || rec.entry.id;
    setCopyStatus(ok ? `已复制购买链接：${name}` : "复制失败，请长按链接手动复制");
  };

  const onCopyResultJson = async () => {
    if (activeRecs.length === 0) {
      setCopyStatus("推荐尚未就绪");
      return;
    }
    const result = toStackResult({
      lutMode: activeLut,
      slots: activeRecs,
      previewRelpath: imported?.previewUrl?.startsWith("./")
        ? imported.previewUrl.replace(/^\.\//, "")
        : imported
          ? null
          : "stack-smoke/preview.png",
      model3mfRelpath: imported?.modelUrl?.startsWith("./")
        ? imported.modelUrl.replace(/^\.\//, "")
        : imported
          ? null
          : "stack-smoke/smoke_rybw_sample_logo.3mf",
      previewDataUrl: imported?.previewUrl?.startsWith("data:") ? imported.previewUrl : null,
      model3mfDataUrl: imported?.modelUrl?.startsWith("data:") ? imported.modelUrl : null,
      createdAt: imported?.createdAt,
    });
    const ok = await copyText(`${JSON.stringify(result, null, 2)}\n`);
    setCopyStatus(ok ? "已复制 stack-result JSON（含 match_tier / alternates）" : "复制失败");
  };

  const onResetImport = () => {
    setImported(null);
    setSlotOrder(null);
    setPreviewOn(true);
    setView("split");
    setImportStatus("已恢复烟测静态结果");
  };

  const onSlotDrop = (index: number) => {
    const from = dragFrom.current;
    dragFrom.current = null;
    if (from === null) return;
    setSlotOrder(moveSlot(orderedSlots.map((slot) => slot.slot), from, index));
  };

  return (
    <section className="lumina-stack">
      <header className="lumina-top">
        <div className="topbar-title">
          <h1>叠色（本机引擎）</h1>
          <p className="topbar-sub">上传图后在本机生成模型再回传。本站不跑 GPL 叠色引擎</p>
        </div>
        <nav className="lumina-top-nav" aria-label="页面导航">
          <a href="#/" className="nav-link">色卡浏览</a>
          <a href="#/plan" className="nav-link">图片配色</a>
          <a href="#/cost" className="nav-link">打印成本</a>
          <a className="nav-link" href={SOURCE_URL} target="_blank" rel="noreferrer">源码</a>
        </nav>
      </header>

      <div className="lumina-stack-main">
        <aside className="lumina-stack-col" aria-label="图像导入和基础设置">
          <div className={`${cardClass} lumina-panel`}>
            <h2 className={settingsGroupHeadingClass}>导入</h2>
            <ImageUpload
              accept="image/png,image/jpeg,image/webp,image/gif"
              preview={previewUrl ?? undefined}
              onFileSelect={(file) => {
                setImage(file);
                setStatus(null);
              }}
            />

            <label className="field">
              <span className="field-label">LUT / 耗材</span>
              <select
                aria-label="LUT 色模式"
                className={workstationInputClass}
                value={mode}
                disabled={trayMap === null}
                onChange={(event) => {
                  setMode(event.target.value as StackLutMode);
                  setSlotOrder(null);
                }}
              >
                <option value="RYBW">RYBW 耗材档案{trayMap ? `（${trayMap.palettes.RYBW.label}）` : ""}</option>
                <option value="CMYW">CMYW 耗材档案{trayMap ? `（${trayMap.palettes.CMYW.label}）` : ""}</option>
              </select>
            </label>
            {loadError && <p className="empty-state">托盘映射加载失败</p>}

            <div className="stack-size-row">
              <label className="field">
                <span className="field-label">层高（mm）</span>
                <input
                  className={workstationInputClass}
                  type="number"
                  min={0.04}
                  step={0.04}
                  aria-label="层高（mm）"
                  value={layerHeightMm}
                  onChange={(event) => setLayerHeightMm(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span className="field-label">底板</span>
                <select
                  className={workstationInputClass}
                  aria-label="底板尺寸"
                  value={bedId}
                  onChange={(event) => setBedId(event.target.value as (typeof BED_PRESETS)[number]["id"])}
                >
                  {BED_PRESETS.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div aria-label="烟测模型与推荐色">
              <h2 className={settingsGroupHeadingClass}>四色槽</h2>
              <p className="stack-disclaimer">拖动色块排序。推荐色和购买链来自当前色卡目录。</p>
              {catalogError && <p className="empty-state">目录加载失败，无法推荐色卡</p>}
              {!catalogError && catalog === null && <p className="empty-state">正在读取色卡目录并匹配槽位…</p>}
              <div aria-label="四槽推荐色卡">
                <ul className="stack-slot-list" aria-label="四色槽">
                  {orderedSlots.map((slot, index) => {
                    const rec = activeRecs.find((item) => item.slot === slot.slot);
                    const name = rec ? rec.entry.zh || rec.entry.en || rec.entry.id : slot.name_zh;
                    return (
                      <li
                        key={`${mode}-${slot.slot}`}
                        className="stack-slot-row"
                        draggable
                        data-slot={slot.slot}
                        onDragStart={() => {
                          dragFrom.current = index;
                        }}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => {
                          event.preventDefault();
                          onSlotDrop(index);
                        }}
                      >
                        <span className="stack-drag" aria-hidden="true">↕</span>
                        <span className="stack-swatch" style={{ background: rec?.engine_hex ?? slot.hex }} title="槽位色" />
                        {rec && (
                          <span className="stack-swatch" style={{ background: rec.catalog_hex }} title="推荐色卡" />
                        )}
                        <div className="stack-rec-main">
                          <strong>
                            {slot.slot} {slot.name_zh}
                            {rec ? ` · ${name}` : ""}
                          </strong>
                          <span className="stack-slot-meta">
                            {slot.catalog_id}
                            {rec ? ` · ${rec.entry.id}` : ""}
                            {rec ? ` · ΔE ${formatDelta(rec.delta_e)}` : ""}
                            {rec?.purchase_is_pdd ? " · PDD 真链" : ""}
                            {rec ? ` · ${tierLabel(rec.match_tier)}` : ""}
                          </span>
                          {rec && <span className="stack-match-reason">{rec.match_reason}</span>}
                          {rec && rec.alternates.length > 0 && (
                            <ul className="stack-alt-list" aria-label={`${slot.slot} 备选`}>
                              {rec.alternates.map((alt) => (
                                <li key={`${slot.slot}-alt-${alt.entry.id}`}>
                                  备选：{alt.entry.zh || alt.entry.en || alt.entry.id}（{alt.entry.id}）· ΔE{" "}
                                  {formatDelta(alt.delta_e)} · {tierLabel(alt.match_tier)}
                                  {alt.purchase_is_pdd ? " · PDD" : ""}
                                </li>
                              ))}
                            </ul>
                          )}
                          {rec && (
                            <div className="stack-rec-actions">
                              <button type="button" className="btn btn-ghost" onClick={() => void onCopyBuy(rec)}>
                                复制购买链接
                              </button>
                              {rec.purchase_url !== null ? (
                                <a className="nav-link" href={rec.purchase_url} target="_blank" rel="noreferrer">
                                  打开购买
                                </a>
                              ) : (
                                <span className="stack-slot-meta">无购买链</span>
                              )}
                            </div>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
              {copyStatus && (
                <p className="toast" role="status">
                  {copyStatus}
                </p>
              )}
            </div>
          </div>
        </aside>

        <div className="lumina-stack-stage" aria-label="叠色预览">
          <div className={`${cardClass} stack-stage-card`}>
            {view === "bed" && (
              <StackBed
                bedWidthMm={bed.width}
                bedHeightMm={bed.height}
                artworkUrl={bedArtwork}
                artworkWidthMm={widthMm}
                artworkHeightMm={heightMm}
              />
            )}
            {view === "original" &&
              (originalSrc ? (
                <figure className="stack-solo">
                  <img src={originalSrc} alt="原图" />
                  <figcaption>{usingFixture ? "烟测原图" : "原图"}</figcaption>
                </figure>
              ) : (
                <p className="empty-state">还没有原图</p>
              ))}
            {view === "stacked" &&
              (stackedSrc ? (
                <figure className="stack-solo">
                  <img src={stackedSrc} alt="叠色预览图" />
                  <figcaption>叠色结果</figcaption>
                </figure>
              ) : (
                <p className="empty-state">还没有叠色结果。回传 JSON 后会显示在这里。</p>
              ))}
            {view === "split" && (
              <div className="stack-split">
                <figure className="stack-solo">
                  {originalSrc ? (
                    <img src={originalSrc} alt={usingFixture ? "烟测原图" : "原图"} />
                  ) : (
                    <p className="empty-state">无原图</p>
                  )}
                  <figcaption>原图</figcaption>
                </figure>
                <figure className="stack-solo">
                  {stackedSrc ? (
                    <img src={stackedSrc} alt="叠色预览图" />
                  ) : (
                    <p className="empty-state">无叠色结果</p>
                  )}
                  <figcaption>叠色结果</figcaption>
                </figure>
              </div>
            )}
            {activeModelUrl && (
              <div className="stack-stage-actions">
                <a className="nav-link" href={activeModelUrl} download={activeModelName}>
                  下载 3MF 模型
                </a>
              </div>
            )}
          </div>
        </div>

        <aside className="lumina-stack-col" aria-label="任务参数">
          <div className={`${cardClass} lumina-panel`}>
            <h2 className={settingsGroupHeadingClass}>预览参数</h2>
            <label className="field">
              <span className="field-label">预览方式</span>
              <select
                aria-label="预览方式"
                className={workstationInputClass}
                value={view}
                onChange={(event) => setView(event.target.value as PreviewView)}
              >
                <option value="bed">热床</option>
                <option value="original">原图</option>
                <option value="stacked">叠色结果</option>
                <option value="split">并排</option>
              </select>
            </label>
            <div className="stack-size-row">
              <label className="field">
                <span className="field-label">宽（mm）</span>
                <input
                  className={workstationInputClass}
                  type="number"
                  min={1}
                  step={1}
                  aria-label="宽（mm）"
                  value={widthMm}
                  onChange={(event) => setWidthMm(Number(event.target.value))}
                />
              </label>
              <label className="field">
                <span className="field-label">高（mm）</span>
                <input
                  className={workstationInputClass}
                  type="number"
                  min={1}
                  step={1}
                  aria-label="高（mm）"
                  value={heightMm}
                  onChange={(event) => setHeightMm(Number(event.target.value))}
                />
              </label>
            </div>
            <p className="stack-disclaimer">
              层高 {layerHeightMm.toFixed(2)} mm · 底板 {bed.label}。这两项留在本页；任务包仍只写尺寸和槽位。
            </p>
            <div className="stack-actions">
              <Button label="预览" onClick={onPreview} />
              <Button label="生成 3MF" variant="primary" onClick={() => void onDownload()} disabled={busy} loading={busy} />
            </div>
            {status && (
              <p className="toast" role="status">
                {status}
              </p>
            )}

            <button
              type="button"
              className="stack-advanced-toggle ghost-control"
              aria-expanded={advancedOpen}
              aria-controls="stack-advanced"
              onClick={() => setAdvancedOpen((open) => !open)}
            >
              <span>高级</span>
              <DisclosureChevron expanded={advancedOpen} />
            </button>
            {advancedOpen && (
              <div id="stack-advanced" className="stack-advanced">
                <h3 className={settingsGroupHeadingClass}>流程</h3>
                <ol className="stack-steps">
                  <li>在本页选 LUT（CMYW / RYBW）与期望尺寸，可选上传原图。</li>
                  <li>下载本机任务包（zip：job.json + 原图）。</li>
                  <li>在 Mac 打开 Lumina（`python api_server.py`），或跑 `scripts/run_lumina_stack_job.py` 骨架。</li>
                  <li>把 lumina-stack-result JSON（可含 preview/3MF 的 relpath 或 base64）拖入或粘贴到下方；本页立刻重算推荐色与购买链。</li>
                </ol>
                <p className="stack-note" role="note">
                  与「图片配色」不同：配色是表面主色 ΔE；叠色是四根基础料层叠逼近整图。Preferred 系列 ΔE &gt; 8
                  时自动回退同品牌其他系列，并保留 LUT 名义色为备选。
                </p>
                <div
                  className={`stack-import${dragOver ? " stack-import-drag" : ""}`}
                  aria-label="回传导入"
                  onDragEnter={(event) => {
                    event.preventDefault();
                    setDragOver(true);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={onDrop}
                >
                  <h3 className={settingsGroupHeadingClass}>回传自动刷新</h3>
                  <p className="stack-disclaimer">
                    拖入 / 选择 / 粘贴 lumina-stack-result JSON。预览支持 preview_relpath、preview_data_url、preview_base64；3MF
                    同理。槽位 engine_hex 会按当前色卡目录重算推荐。
                  </p>
                  <label className="field">
                    <span className="field-label">导入 JSON 文件</span>
                    <input
                      type="file"
                      accept="application/json,.json,text/plain"
                      aria-label="导入回传 JSON 文件"
                      onChange={onImportInputChange}
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">或粘贴 JSON</span>
                    <textarea
                      aria-label="粘贴回传 JSON"
                      className="stack-import-textarea"
                      rows={6}
                      value={importText}
                      onChange={(event) => setImportText(event.target.value)}
                      placeholder='{"kind":"lumina-stack-result","lut_mode":"RYBW","slots":[...]}'
                    />
                  </label>
                  <div className="stack-actions">
                    <button
                      type="button"
                      className="btn"
                      onClick={() => applyImportText(importText, "粘贴")}
                      disabled={catalog === null || importText.trim() === ""}
                    >
                      应用粘贴内容
                    </button>
                    <button type="button" className="btn btn-ghost" onClick={onResetImport} disabled={imported === null}>
                      恢复烟测
                    </button>
                    <button type="button" className="btn btn-ghost" onClick={() => void onCopyResultJson()}>
                      复制回传 JSON 样例
                    </button>
                  </div>
                  {importStatus && (
                    <p className="toast" role="status">
                      {importStatus}
                    </p>
                  )}
                </div>
                <p className="stack-disclaimer">
                  热床几何、纹理和面板样式来自 Lumina-Layers（Lumina Studio），AGPL-3.0-only：
                  https://github.com/lumina-layer-studio/Lumina-Layers
                </p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
