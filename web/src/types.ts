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
  price: string | null;
}

export interface WebCatalog {
  generated_at: string;
  brands: { slug: string; name: string }[];
  entries: WebEntry[];
}
