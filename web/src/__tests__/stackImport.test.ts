import { describe, expect, it } from "vitest";
import catalog from "../../public/web-catalog.json";
import {
  applyStackResult,
  parseStackResultPayload,
  parseStackResultText,
  resolvePreviewUrl,
} from "../stackImport";
import type { WebCatalog } from "../types";

const entries = (catalog as WebCatalog).entries;

const sample = {
  schema_version: 1 as const,
  kind: "lumina-stack-result" as const,
  created_at: "2026-11-09T18:00:00+09:00",
  lut_mode: "RYBW" as const,
  source_job_kind: "lumina-stack-job" as const,
  preview_relpath: "stack-smoke/preview.png",
  model_3mf_relpath: "stack-smoke/smoke_rybw_sample_logo.3mf",
  slots: [
    {
      extruder: 1,
      slot: "W",
      name_zh: "白",
      name_en: "White",
      engine_hex: "#D7D2CF",
      recommended_id: "stale",
      recommended_hex: "#000000",
      recommended_name: "stale",
      delta_e: 99,
      purchase_url: null,
      purchase_is_pdd: false,
    },
    {
      extruder: 2,
      slot: "R",
      name_zh: "红",
      name_en: "Red",
      engine_hex: "#E94A39",
      recommended_id: "stale",
      recommended_hex: "#000000",
      recommended_name: "stale",
      delta_e: 99,
      purchase_url: null,
      purchase_is_pdd: false,
    },
    {
      extruder: 3,
      slot: "Y",
      name_zh: "黄",
      name_en: "Yellow",
      engine_hex: "#ECEF35",
      recommended_id: "stale",
      recommended_hex: "#000000",
      recommended_name: "stale",
      delta_e: 99,
      purchase_url: null,
      purchase_is_pdd: false,
    },
    {
      extruder: 4,
      slot: "B",
      name_zh: "蓝",
      name_en: "Blue",
      engine_hex: "#3451B1",
      recommended_id: "stale",
      recommended_hex: "#000000",
      recommended_name: "stale",
      delta_e: 99,
      purchase_url: null,
      purchase_is_pdd: false,
    },
  ],
  note: "test",
};

describe("stackImport", () => {
  it("parses valid payload and rejects bad kind", () => {
    expect(parseStackResultPayload(sample).ok).toBe(true);
    expect(parseStackResultPayload({ kind: "nope" }).ok).toBe(false);
    expect(parseStackResultText("{").ok).toBe(false);
  });

  it("resolves preview from relpath or base64", () => {
    const fromPath = parseStackResultPayload(sample);
    expect(fromPath.ok).toBe(true);
    if (fromPath.ok) {
      expect(resolvePreviewUrl(fromPath.result)).toBe("./stack-smoke/preview.png");
    }
    const withB64 = {
      ...sample,
      preview_relpath: null,
      preview_base64: "iVBORw0KGgo=",
    };
    const parsed = parseStackResultPayload(withB64);
    expect(parsed.ok).toBe(true);
    if (parsed.ok) {
      expect(resolvePreviewUrl(parsed.result)?.startsWith("data:image/png;base64,")).toBe(true);
    }
  });

  it("re-recommends against live catalog ignoring stale recommended_*", () => {
    const parsed = parseStackResultPayload(sample);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const view = applyStackResult(parsed.result, entries, "unit-test.json");
    expect(view.slots.find((s) => s.slot === "R")?.entry.id).toBe(
      "bambu-lab/pla-matte/scarlet-red-11200",
    );
    expect(view.previewUrl).toContain("stack-smoke/preview.png");
    expect(view.sourceLabel).toBe("unit-test.json");
  });
});
