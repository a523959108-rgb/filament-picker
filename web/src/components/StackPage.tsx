import { useCallback, useEffect, useMemo, useState } from "react";
import type { ChangeEvent, DragEvent, JSX } from "react";
import { loadCatalog } from "../catalog";
import { copyText } from "../marketPrice";
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

const DEFAULT_SIZE_MM = 100;

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
  const [image, setImage] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [importText, setImportText] = useState("");
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [imported, setImported] = useState<ImportedStackView | null>(null);

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

  const smokeRecs: SlotRecommendation[] = useMemo(() => {
    if (catalog === null) return [];
    return recommendSlots(SMOKE_RYBW_SLOTS, catalog.entries ?? [], {
      brandSlug: "bambu-lab",
      seriesIncludes: "PLA Basic",
      material: "PLA",
    });
  }, [catalog]);

  const activeRecs = imported?.slots ?? smokeRecs;
  const activePreview = imported?.previewUrl ?? SMOKE_PREVIEW_URL;
  const activeModelUrl = imported?.modelUrl ?? SMOKE_MODEL_3MF_URL;
  const activeModelName = imported?.modelDownloadName ?? "smoke_rybw_sample_logo.3mf";
  const activeLut = imported?.lutMode ?? "RYBW";

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
      const view = applyStackResult(parsed.result, catalog.entries ?? [], sourceLabel);
      setImported(view);
      setMode(view.lutMode);
      setImportStatus(
        `已导入并刷新：${sourceLabel} · ${view.lutMode} · ${view.slots.length} 槽（推荐按当前目录重算）`,
      );
    },
    [catalog],
  );

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setImage(event.target.files?.[0] ?? null);
    setStatus(null);
  };

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
        palette,
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
    setImportStatus("已恢复烟测静态结果");
  };

  return (
    <section className="stack-page">
      <header className="topbar">
        <div className="topbar-title">
          <h1>叠色（本机引擎）</h1>
          <p className="topbar-sub">
            上传图 → 本机 Lumina 生成模型 → 回站导入 JSON 刷新预览/3MF，并用色卡库推荐购买色；本站不跑 GPL 叠色引擎
          </p>
        </div>
        <nav className="topbar-nav" aria-label="页面导航">
          <a href="#/" className="nav-link">
            色卡浏览
          </a>
          <a href="#/plan" className="nav-link">
            图片配色
          </a>
          <a href="#/cost" className="nav-link">
            打印成本
          </a>
        </nav>
      </header>

      <div className="panel stack-panel">
        <h2>流程</h2>
        <ol className="stack-steps">
          <li>在本页选 LUT（CMYW / RYBW）与期望尺寸，可选上传原图。</li>
          <li>下载本机任务包（zip：job.json + 原图）。</li>
          <li>在 Mac 打开 Lumina（`python api_server.py`），或跑 `scripts/run_lumina_stack_job.py` 骨架。</li>
          <li>
            把 <code>lumina-stack-result</code> JSON（可含 preview/3MF 的 relpath 或 base64）拖入/粘贴到下方；本页立刻重算推荐色与购买链。
          </li>
        </ol>
        <p className="stack-note" role="note">
          与「图片配色」不同：配色是表面主色 ΔE；叠色是四根基础料层叠逼近整图。Preferred 系列 ΔE &gt; 8
          时自动回退同品牌其他系列，并保留 LUT 名义色为备选。
        </p>
      </div>

      <div
        className={`panel stack-panel stack-import${dragOver ? " stack-import-drag" : ""}`}
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
        <h2>回传自动刷新</h2>
        <p className="stack-disclaimer">
          拖入 / 选择 / 粘贴 <code>lumina-stack-result</code> JSON。预览支持{" "}
          <code>preview_relpath</code>、<code>preview_data_url</code>、<code>preview_base64</code>；3MF
          同理。槽位 <code>engine_hex</code> 会按<strong>当前色卡目录</strong>重算推荐（不盲信 JSON 里旧的
          recommended_*）。
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
        </div>
        {importStatus && (
          <p className="toast" role="status">
            {importStatus}
          </p>
        )}
      </div>

      <div className="panel stack-panel" aria-label="烟测模型与推荐色">
        <h2>{imported ? `回传结果 · ${activeLut}` : "烟测模型 · RYBW"}</h2>
        <p className="stack-disclaimer">
          {imported
            ? `来源：${imported.sourceLabel} · ${imported.createdAt}。推荐已按当前目录级联匹配（Basic → 同品牌 → 跨品牌备选）。`
            : "静态嵌入 2026-11-09 本机烟测产物（preview + 3MF）。红槽若 Basic ΔE 超阈，自动回退同品牌更近色并标清理由。"}
        </p>
        <div className="stack-smoke-grid">
          <figure className="stack-smoke-figure">
            {activePreview ? (
              <img src={activePreview} alt="叠色预览图" className="stack-smoke-img" />
            ) : (
              <p className="empty-state">回传未含预览图</p>
            )}
            <figcaption>Lumina 预览（层叠结果，非原图）</figcaption>
          </figure>
          {!imported && (
            <figure className="stack-smoke-figure">
              <img src={SMOKE_INPUT_URL} alt="烟测原图" className="stack-smoke-img stack-smoke-img-small" />
              <figcaption>原图对照</figcaption>
            </figure>
          )}
        </div>
        <div className="stack-actions">
          {activeModelUrl ? (
            <a className="btn" href={activeModelUrl} download={activeModelName}>
              下载 3MF 模型
            </a>
          ) : (
            <span className="stack-slot-meta">回传未含 3MF</span>
          )}
          <button type="button" className="btn btn-ghost" onClick={() => void onCopyResultJson()}>
            复制回传 JSON 样例
          </button>
        </div>

        {catalogError && <p className="empty-state">目录加载失败，无法推荐色卡</p>}
        {!catalogError && catalog === null && <p className="empty-state">正在读取色卡目录并匹配槽位…</p>}
        {!catalogError && catalog !== null && activeRecs.length > 0 && (
          <>
            <h3 className="stack-slots-title">四槽推荐色卡（引用选色站数据库）</h3>
            <ul className="stack-rec-list" aria-label="四槽推荐色卡">
              {activeRecs.map((rec) => {
                const name = rec.entry.zh || rec.entry.en || rec.entry.id;
                return (
                  <li key={`rec-${rec.slot}-${rec.entry.id}`} className="stack-rec-row">
                    <span className="stack-swatch-pair" aria-hidden="true">
                      <span className="stack-swatch" style={{ background: rec.engine_hex }} title="引擎槽位" />
                      <span className="stack-swatch" style={{ background: rec.catalog_hex }} title="推荐色卡" />
                    </span>
                    <div className="stack-rec-main">
                      <strong>
                        E{rec.extruder} · {rec.slot} {rec.name_zh}
                      </strong>
                      <span className="stack-slot-meta">
                        引擎 {rec.engine_hex} → 推荐 {name}（{rec.entry.id}）· 色卡 {rec.catalog_hex} · ΔE{" "}
                        {formatDelta(rec.delta_e)}
                        {rec.purchase_is_pdd ? " · PDD 真链" : ""} · {tierLabel(rec.match_tier)}
                      </span>
                      <span className="stack-match-reason">{rec.match_reason}</span>
                      {rec.alternates.length > 0 && (
                        <ul className="stack-alt-list" aria-label={`${rec.slot} 备选`}>
                          {rec.alternates.map((alt) => (
                            <li key={`${rec.slot}-alt-${alt.entry.id}`}>
                              备选：{alt.entry.zh || alt.entry.en || alt.entry.id}（{alt.entry.id}）· ΔE{" "}
                              {formatDelta(alt.delta_e)} · {tierLabel(alt.match_tier)}
                              {alt.purchase_is_pdd ? " · PDD" : ""}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
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
                  </li>
                );
              })}
            </ul>
          </>
        )}
        {copyStatus && (
          <p className="toast" role="status">
            {copyStatus}
          </p>
        )}
      </div>

      <div className="panel stack-panel" aria-label="任务参数">
        <h2>下一单任务参数</h2>
        {loadError && <p className="empty-state">托盘映射加载失败</p>}
        {!loadError && trayMap === null && <p className="empty-state">正在读取四色托盘映射…</p>}
        {!loadError && trayMap !== null && palette !== null && (
          <>
            <p className="stack-disclaimer">{trayMap.disclaimer}</p>
            <label className="field">
              <span className="field-label">LUT 色模式</span>
              <select
                aria-label="LUT 色模式"
                value={mode}
                onChange={(event) => setMode(event.target.value as StackLutMode)}
              >
                <option value="CMYW">CMYW（{trayMap.palettes.CMYW.label}）</option>
                <option value="RYBW">RYBW（{trayMap.palettes.RYBW.label}）</option>
              </select>
            </label>
            <div className="stack-size-row">
              <label className="field">
                <span className="field-label">宽（mm）</span>
                <input
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
                  type="number"
                  min={1}
                  step={1}
                  aria-label="高（mm）"
                  value={heightMm}
                  onChange={(event) => setHeightMm(Number(event.target.value))}
                />
              </label>
            </div>
            <label className="field">
              <span className="field-label">原图（可选）</span>
              <input type="file" accept="image/*" aria-label="原图" onChange={onFileChange} />
            </label>
            <h3 className="stack-slots-title">期望槽位 · {mode}</h3>
            <ul className="stack-slot-list">
              {palette.slots.map((slot) => (
                <li key={`${mode}-${slot.slot}`} className="stack-slot-row">
                  <span className="stack-swatch" style={{ background: slot.hex }} aria-hidden="true" />
                  <span>
                    <strong>{slot.slot}</strong> {slot.name_zh}（{slot.name_en}）
                    <span className="stack-slot-meta">
                      {" "}
                      · {slot.catalog_id} · {slot.hex} · {slot.status}
                      {slot.match_reason ? ` · ${slot.match_reason}` : ""}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <div className="stack-actions">
              <button type="button" className="btn" onClick={onDownload} disabled={busy}>
                下载本机任务包
              </button>
            </div>
            {status && (
              <p className="toast" role="status">
                {status}
              </p>
            )}
            {previewUrl !== null && (
              <figure className="stack-smoke-figure">
                <img src={previewUrl} alt="已选原图预览（非叠色结果）" className="stack-smoke-img" />
                <figcaption>仅原图预览，不是叠色输出</figcaption>
              </figure>
            )}
          </>
        )}
      </div>
    </section>
  );
}
