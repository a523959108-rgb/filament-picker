/** Local Lumina stack-job helpers. No GPL engine code. */

export type StackLutMode = "CMYW" | "RYBW";

export type TraySlot = {
  slot: string;
  name_zh: string;
  name_en: string;
  catalog_id: string;
  hex: string;
  code: string;
  status: string;
  /** Human-readable why this catalog_id was chosen (ΔE / fallback). */
  match_reason?: string;
  /** Optional LUT-nominal id when primary is a fallback. */
  lut_nominal_id?: string;
};

export type TrayPalette = {
  label: string;
  lut_hints: string[];
  slots: TraySlot[];
  /** Optional engine hex from a smoke/generate pass, keyed by slot letter. */
  smoke_engine_hex?: Record<string, string>;
};

export type FourColorTrayMap = {
  schema_version: 1;
  updated_at: string;
  brand_preference: string;
  series_preference: string;
  disclaimer: string;
  palettes: Record<StackLutMode, TrayPalette>;
};

export type StackJob = {
  schema_version: 1;
  kind: "lumina-stack-job";
  created_at: string;
  lut_mode: StackLutMode;
  lut_hints: string[];
  size_mm: { width: number; height: number };
  slots: TraySlot[];
  image_filename: string | null;
  engine: {
    run_on: "local-lumina";
    start_hints: string[];
    note: string;
  };
  smoke_preview: null;
};

export const TRAY_MAP_URL = "./four-color-tray-map.json";

export async function loadTrayMap(url: string = TRAY_MAP_URL): Promise<FourColorTrayMap> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`tray map HTTP ${response.status}`);
  }
  return (await response.json()) as FourColorTrayMap;
}

export function buildStackJob(input: {
  mode: StackLutMode;
  palette: TrayPalette;
  widthMm: number;
  heightMm: number;
  imageFilename: string | null;
  createdAt?: string;
}): StackJob {
  const createdAt =
    input.createdAt ??
    new Date().toLocaleString("sv-SE", { timeZone: "Asia/Tokyo" }).replace(" ", "T") + "+09:00";
  return {
    schema_version: 1,
    kind: "lumina-stack-job",
    created_at: createdAt,
    lut_mode: input.mode,
    lut_hints: [...input.palette.lut_hints],
    size_mm: { width: input.widthMm, height: input.heightMm },
    slots: input.palette.slots.map((slot) => ({ ...slot })),
    image_filename: input.imageFilename,
    engine: {
      run_on: "local-lumina",
      start_hints: ["python main.py", "python api_server.py"],
      note: "GPL 引擎只在本机 Lumina 运行；本包仅元数据与可选原图，不嵌进选色站。",
    },
    smoke_preview: null,
  };
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[i] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    c = CRC_TABLE[(c ^ bytes[i]!) & 0xff]! ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u16(value: number): Uint8Array {
  const out = new Uint8Array(2);
  out[0] = value & 0xff;
  out[1] = (value >>> 8) & 0xff;
  return out;
}

function u32(value: number): Uint8Array {
  const out = new Uint8Array(4);
  out[0] = value & 0xff;
  out[1] = (value >>> 8) & 0xff;
  out[2] = (value >>> 16) & 0xff;
  out[3] = (value >>> 24) & 0xff;
  return out;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

/** Store-only ZIP (no compression). No extra npm dependency. */
export function buildZip(files: { name: string; data: Uint8Array }[]): Blob {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const crc = crc32(file.data);
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
      file.data,
    ]);
    const central = concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ]);
    localParts.push(local);
    centralParts.push(central);
    offset += local.length;
  }

  const centralDirectory = concat(centralParts);
  const end = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDirectory.length),
    u32(offset),
    u16(0),
  ]);
  const bytes = concat([...localParts, centralDirectory, end]);
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy.buffer], { type: "application/zip" });
}

export async function buildJobPackageZip(job: StackJob, image: File | null): Promise<Blob> {
  const encoder = new TextEncoder();
  const files: { name: string; data: Uint8Array }[] = [
    {
      name: "job.json",
      data: encoder.encode(`${JSON.stringify(job, null, 2)}\n`),
    },
  ];
  if (image !== null) {
    const buffer = new Uint8Array(await image.arrayBuffer());
    files.push({ name: job.image_filename ?? image.name, data: buffer });
  }
  return buildZip(files);
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}
