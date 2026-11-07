import { CATALOG_URL } from "./config";
import type { WebCatalog } from "./types";

export async function loadCatalog(url: string = CATALOG_URL): Promise<WebCatalog> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`catalog ${response.status}`);
  }
  return (await response.json()) as WebCatalog;
}
