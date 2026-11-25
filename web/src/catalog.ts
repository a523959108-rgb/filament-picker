import { CATALOG_URL } from "./config";
import type { WebCatalog } from "./types";

type FetchFn = typeof fetch;

const catalogCache = new WeakMap<FetchFn, Map<string, Promise<WebCatalog>>>();

export function clearCatalogCache(): void {
  const map = catalogCache.get(globalThis.fetch);
  map?.clear();
}

export async function loadCatalog(url: string = CATALOG_URL): Promise<WebCatalog> {
  const fetchImpl = globalThis.fetch;
  let byUrl = catalogCache.get(fetchImpl);
  if (byUrl === undefined) {
    byUrl = new Map<string, Promise<WebCatalog>>();
    catalogCache.set(fetchImpl, byUrl);
  }
  const existing = byUrl.get(url);
  if (existing !== undefined) {
    return existing;
  }
  const pending = (async () => {
    const response = await fetchImpl(url, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`catalog ${response.status}`);
    }
    return (await response.json()) as WebCatalog;
  })().catch((error: unknown) => {
    byUrl.delete(url);
    throw error;
  });
  byUrl.set(url, pending);
  return pending;
}
