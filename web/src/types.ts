export interface WebEntry {
  id: string;
  b: string;
  s: string;
  m: "PLA" | "PETG";
  en: string | null;
  zh: string | null;
  code: string | null;
  py: string | null;
  pyi: string | null;
  fam: string;
  eff: string[];
  hex: string[];
  src: "official" | "store_swatch" | "image_extracted" | "manual" | null;
  conf: number | null;
  url: string;
  alt_url: string | null;
  price: string | null;
  img: string | null;
}

export interface WebCatalog {
  generated_at: string;
  brands: { slug: string; name: string }[];
  entries: WebEntry[];
}

export interface PlanResult {
  schema_version: 1;
  request_id: string;
  status: "ok" | "error";
  created_at: string;
  finished_at: string;
  elapsed_ms: number;
  error: {
    code:
      | "INVALID_REQUEST"
      | "IMAGE_MISSING"
      | "IMAGE_UNREADABLE"
      | "IMAGE_TOO_SMALL"
      | "NO_FOREGROUND"
      | "NO_MATCH"
      | "CATALOG_ERROR"
      | "INTERNAL";
    message_zh: string;
  } | null;
  params: {
    max_colors: number;
    ams_slots: number;
    n_colors: number;
    materials: ("PLA" | "PETG")[];
    brands: string[];
    allow_approx: boolean;
    keep_small: boolean;
    per_color: number;
    note_parsed: Record<string, unknown>;
  };
  palette: {
    index: number;
    hex: string;
    lab: number[];
    share: number;
  }[];
  matches: {
    target_index: number;
    picks: {
      id: string;
      brand_name: string;
      series_name: string;
      name_display: string;
      hex: string;
      hex_source: "official" | "store_swatch" | "image_extracted" | "manual";
      delta_e: number;
      label: "几乎一样" | "接近" | "勉强";
      is_approx: boolean;
      url: string;
      alt_url?: string | null;
      price_text: string | null;
    }[];
  }[];
  single_series_option: {
    brand_name: string;
    series_name: string;
    max_delta_e: number;
    picks: { target_index: number; id: string; delta_e: number }[];
  } | null;
  slots_used: number;
  card_path: string | null;
  card_url: string | null;
  reply_markdown: string;
  warnings: string[];
  context: Record<string, unknown>;
  catalog_generated_at: string | null;
}
