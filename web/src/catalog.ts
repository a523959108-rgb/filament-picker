import { CATALOG_URL } from "./config";
import type { WebCatalog } from "./types";

const catalogPromises = new WeakMap<typeof fetch, Map<string, Promise<WebCatalog>>>();

export function loadCatalog(url: string = CATALOG_URL): Promise<WebCatalog> {
  const fetcher = globalThis.fetch;
  let byUrl = catalogPromises.get(fetcher);
  if (byUrl === undefined) {
    byUrl = new Map();
    catalogPromises.set(fetcher, byUrl);
  }
  const cached = byUrl.get(url);
  if (cached !== undefined) return cached;
  const promise = (async () => {
    const response = await fetcher(url, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`catalog ${response.status}`);
    }
    return (await response.json()) as WebCatalog;
  })().catch((error) => {
    byUrl.delete(url);
    throw error;
  });
  byUrl.set(url, promise);
  return promise;
}
