import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "./catalog";
import { FAMILIES } from "./config";
import { Filters } from "./components/Filters";
import { SwatchGrid } from "./components/SwatchGrid";
import { buildIndex, EMPTY_FILTER, query } from "./search";
import type { FilterState } from "./search";
import type { WebCatalog } from "./types";

function routeFromHash(): string {
  return window.location.hash;
}

export default function App(): JSX.Element {
  const [route, setRoute] = useState(routeFromHash);
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTER);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (route === "#/plan") return;
    let active = true;
    loadCatalog()
      .then((value) => {
        if (active) setCatalog(value);
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => {
      active = false;
    };
  }, [route]);

  const index = useMemo(() => (catalog === null ? null : buildIndex(catalog.entries)), [catalog]);

  if (route === "#/plan") {
    return <main className="page"><p>图片配色（T24）</p></main>;
  }
  if (loadError) {
    return <main className="page"><p>目录加载失败</p></main>;
  }
  if (catalog === null) {
    return <main className="page"><p>目录加载中…</p></main>;
  }
  const entries = index === null ? [] : query(index, catalog, searchText, filters);
  return (
    <main className="page">
      <h1>耗材选色站</h1>
      <label>
        搜索
        <input
          type="search"
          aria-label="搜索"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
        />
      </label>
      <Filters brands={catalog.brands} families={[...FAMILIES]} value={filters} onChange={setFilters} />
      <SwatchGrid entries={entries} brands={catalog.brands} />
    </main>
  );
}
