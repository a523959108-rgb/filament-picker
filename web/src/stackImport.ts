/** Parse / apply lumina-stack-result payloads for #/stack live refresh. No GPL. */

import type { StackLutMode } from "./stackJob";
import {
  recommendSlots,
  type SlotRecommendation,
  type SmokeSlotTarget,
  type StackResult,
} from "./stackRecommend";
import type { WebEntry } from "./types";

export type ImportedStackView = {
  lutMode: StackLutMode;
  createdAt: string;
  previewUrl: string | null;
  modelUrl: string | null;
  modelDownloadName: string;
  slots: SlotRecommendation[];
  note: string;
  sourceLabel: string;
};

function isLutMode(value: unknown): value is StackLutMode {
  return value === "CMYW" || value === "RYBW";
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

function guessImageMime(base64: string): string {
  if (base64.startsWith("/9j/")) return "image/jpeg";
  if (base64.startsWith("UklGR")) return "image/webp";
  return "image/png";
}

function toDataUrl(base64OrDataUrl: string, kind: "image" | "model"): string {
  if (base64OrDataUrl.startsWith("data:")) return base64OrDataUrl;
  if (kind === "model") {
    return `data:application/octet-stream;base64,${base64OrDataUrl}`;
  }
  return `data:${guessImageMime(base64OrDataUrl)};base64,${base64OrDataUrl}`;
}

function publicRelpath(relpath: string): string {
  const cleaned = relpath.replace(/^\.\//, "").replace(/^\/+/, "");
  return `./${cleaned}`;
}

export type ParseStackResultError = { ok: false; message: string };
export type ParseStackResultOk = { ok: true; result: StackResult };
export type ParseStackResultOutcome = ParseStackResultOk | ParseStackResultError;

/** Validate and normalize a lumina-stack-result object (from paste/file). */
export function parseStackResultPayload(raw: unknown): ParseStackResultOutcome {
  if (raw === null || typeof raw !== "object") {
    return { ok: false, message: "回传内容须为 JSON 对象" };
  }
  const obj = raw as Record<string, unknown>;
  if (obj.kind !== "lumina-stack-result") {
    return { ok: false, message: "kind 须为 lumina-stack-result" };
  }
  if (!isLutMode(obj.lut_mode)) {
    return { ok: false, message: "lut_mode 须为 CMYW 或 RYBW" };
  }
  if (!Array.isArray(obj.slots) || obj.slots.length === 0) {
    return { ok: false, message: "slots 不能为空" };
  }

  const slots: StackResult["slots"] = [];
  for (const item of obj.slots) {
    if (item === null || typeof item !== "object") {
      return { ok: false, message: "slots 项格式错误" };
    }
    const slot = item as Record<string, unknown>;
    const engineHex = asString(slot.engine_hex);
    const letter = asString(slot.slot);
    const extruder = typeof slot.extruder === "number" ? slot.extruder : Number(slot.extruder);
    if (engineHex === null || letter === null || !Number.isFinite(extruder)) {
      return { ok: false, message: "每个 slot 需要 extruder / slot / engine_hex" };
    }
    if (!/^#[0-9A-Fa-f]{6}$/.test(engineHex)) {
      return { ok: false, message: `engine_hex 非法：${engineHex}` };
    }
    slots.push({
      extruder,
      slot: letter,
      name_zh: asString(slot.name_zh) ?? letter,
      name_en: asString(slot.name_en) ?? letter,
      engine_hex: engineHex.toUpperCase(),
      recommended_id: asString(slot.recommended_id) ?? "",
      recommended_hex: asString(slot.recommended_hex) ?? "",
      recommended_name: asString(slot.recommended_name) ?? "",
      delta_e: typeof slot.delta_e === "number" ? slot.delta_e : 0,
      purchase_url: asString(slot.purchase_url),
      purchase_is_pdd: Boolean(slot.purchase_is_pdd),
    });
  }

  const result: StackResult = {
    schema_version: 1,
    kind: "lumina-stack-result",
    created_at: asString(obj.created_at) ?? new Date().toISOString(),
    lut_mode: obj.lut_mode,
    source_job_kind: "lumina-stack-job",
    preview_relpath: asString(obj.preview_relpath),
    model_3mf_relpath: asString(obj.model_3mf_relpath),
    preview_data_url: asString(obj.preview_data_url),
    preview_base64: asString(obj.preview_base64),
    model_3mf_data_url: asString(obj.model_3mf_data_url),
    model_3mf_base64: asString(obj.model_3mf_base64),
    slots,
    note: asString(obj.note) ?? "",
  };
  return { ok: true, result };
}

export function parseStackResultText(text: string): ParseStackResultOutcome {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, message: "JSON 解析失败" };
  }
  return parseStackResultPayload(parsed);
}

export function resolvePreviewUrl(result: StackResult): string | null {
  if (result.preview_data_url) return toDataUrl(result.preview_data_url, "image");
  if (result.preview_base64) return toDataUrl(result.preview_base64, "image");
  if (result.preview_relpath) return publicRelpath(result.preview_relpath);
  return null;
}

export function resolveModelUrl(result: StackResult): {
  url: string | null;
  downloadName: string;
} {
  const downloadName =
    (result.model_3mf_relpath ? result.model_3mf_relpath.split("/").pop() : null) ??
    `stack-${result.lut_mode.toLowerCase()}.3mf`;
  if (result.model_3mf_data_url) {
    return { url: toDataUrl(result.model_3mf_data_url, "model"), downloadName };
  }
  if (result.model_3mf_base64) {
    return { url: toDataUrl(result.model_3mf_base64, "model"), downloadName };
  }
  if (result.model_3mf_relpath) {
    return { url: publicRelpath(result.model_3mf_relpath), downloadName };
  }
  return { url: null, downloadName };
}

export function slotsFromResult(result: StackResult): SmokeSlotTarget[] {
  return result.slots.map((slot) => ({
    extruder: slot.extruder,
    slot: slot.slot,
    name_zh: slot.name_zh,
    name_en: slot.name_en,
    engine_hex: slot.engine_hex,
  }));
}

/** Apply imported result: re-recommend against live catalog (ignore stale recommended_*). */
export function applyStackResult(
  result: StackResult,
  entries: WebEntry[],
  sourceLabel: string,
): ImportedStackView {
  const targets = slotsFromResult(result);
  const slots = recommendSlots(targets, entries, {
    brandSlug: "bambu-lab",
    seriesIncludes: "PLA Basic",
    material: "PLA",
  });
  const model = resolveModelUrl(result);
  return {
    lutMode: result.lut_mode,
    createdAt: result.created_at,
    previewUrl: resolvePreviewUrl(result),
    modelUrl: model.url,
    modelDownloadName: model.downloadName,
    slots,
    note: result.note,
    sourceLabel,
  };
}
