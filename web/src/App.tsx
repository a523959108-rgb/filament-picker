import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "./catalog";
import { FAMILIES } from "./config";
import { Filters } from "./components/Filters";
import { ColorDetail } from "./components/ColorDetail";
import { CompareBar } from "./components/CompareBar";
import { SwatchGrid } from "./components/SwatchGrid";
import { PlanPage } from "./components/PlanPage";
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareMessage, setCompareMessage] = useState<string | null>(null);

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
    return <main className="page"><PlanPage /></main>;
  }
  if (loadError) {
    return <main className="page"><p>目录加载失败</p></main>;
  }
  if (catalog === null) {
    return <main className="page"><p>目录加载中…</p></main>;
  }
  const entries = index === null ? [] : query(index, catalog, searchText, filters);
  const selected = selectedId === null ? null : catalog.entries.find((entry) => entry.id === selectedId) ?? null;
  const compareEntries = compareIds
    .map((id) => catalog.entries.find((entry) => entry.id === id))
    .filter((entry): entry is WebCatalog["entries"][number] => entry !== undefined);
  const addCompare = (id: string) => {
    setCompareMessage(null);
    if (compareIds.includes(id)) return;
    if (compareIds.length >= 4) {
      setCompareMessage("最多对比 4 个");
      return;
    }
    setCompareIds([...compareIds, id]);
  };
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
      <SwatchGrid entries={entries} brands={catalog.brands} onSelect={setSelectedId} />
      {compareMessage && <p role="status">{compareMessage}</p>}
      {compareEntries.length > 0 && (
        <CompareBar entries={compareEntries} onRemove={(id) => setCompareIds((current) => current.filter((item) => item !== id))} />
      )}
      {selected && (
        <ColorDetail
          entry={selected}
          catalog={catalog}
          onClose={() => setSelectedId(null)}
          onCompare={addCompare}
        />
      )}
    </main>
  );
}
