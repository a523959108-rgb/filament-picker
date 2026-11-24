import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "./catalog";
import { FAMILIES, defaultStackHash } from "./config";
import { Filters } from "./components/Filters";
import { ColorDetail } from "./components/ColorDetail";
import { CompareBar } from "./components/CompareBar";
import { SwatchGrid } from "./components/SwatchGrid";
import { PlanPage } from "./components/PlanPage";
import { CostPage } from "./components/CostPage";
import { ModelPreview } from "./components/ModelPreview";
import { PhotoPage } from "./components/PhotoPage";
import { SiteHeader } from "./components/SiteHeader";
import { SpecIndex } from "./components/SpecIndex";
import { StackPage } from "./components/StackPage";
import { buildIndex, EMPTY_FILTER, query } from "./search";
import type { FilterState } from "./search";
import type { WebCatalog } from "./types";

function routeFromHash(): string {
  return window.location.hash;
}

function pageFromHash(hash: string): "plan" | "cost" | "stack" | "photo" | "specs" | "catalog" {
  const body = (hash.startsWith("#") ? hash.slice(1) : hash).split("?")[0] ?? "";
  const path = body.replace(/\/+$/, "") || "/";
  if (path === "/plan") return "plan";
  if (path === "/cost") return "cost";
  if (path === "/stack") return "stack";
  if (path === "/photo") return "photo";
  if (path === "/specs") return "specs";
  return "catalog";
}

function CatalogHeader(): JSX.Element {
  return <SiteHeader active="catalog" />;
}

export default function App(): JSX.Element {
  if (window.location.pathname === "/models" || window.location.pathname.startsWith("/models/")) {
    return <ModelPreview />;
  }
  return <CatalogApp />;
}

function CatalogApp(): JSX.Element {
  const [route, setRoute] = useState(
    () => defaultStackHash(window.location.hostname, routeFromHash()) ?? routeFromHash(),
  );
  const page = pageFromHash(route);
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTER);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareMessage, setCompareMessage] = useState<string | null>(null);
  const [brandOpen, setBrandOpen] = useState(false);

  useEffect(() => {
    const onHashChange = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const next = defaultStackHash(window.location.hostname, routeFromHash());
    if (next !== null && routeFromHash() !== next) {
      window.location.hash = next;
    }
  }, []);

  useEffect(() => {
    if (page === "plan" || page === "stack" || page === "photo") return;
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
  }, [page]);

  const index = useMemo(() => (catalog === null ? null : buildIndex(catalog.entries)), [catalog]);
  const effects = useMemo(() => {
    if (catalog === null) return [];
    return [...new Set(catalog.entries.flatMap((entry) => entry.eff))].sort((left, right) =>
      left.localeCompare(right, "zh"),
    );
  }, [catalog]);
  const entries = useMemo(
    () =>
      catalog === null || index === null
        ? []
        : query(index, catalog, searchText, filters),
    [index, catalog, searchText, filters],
  );

  if (page === "plan") {
    return <main className="page"><PlanPage /></main>;
  }
  if (page === "cost") {
    return <main className="page"><CostPage /></main>;
  }
  if (page === "stack") {
    return <StackPage />;
  }
  if (page === "photo") {
    return <main className="page"><PhotoPage /></main>;
  }
  if (page === "specs") {
    return (
      <main className="page catalog-page">
        <CatalogHeader />
        <SpecIndex catalog={catalog} />
      </main>
    );
  }
  if (loadError) {
    return (
      <main className="page">
        <CatalogHeader />
        <p className="panel empty-state">目录加载失败</p>
      </main>
    );
  }
  if (catalog === null) {
    return (
      <main className="page">
        <CatalogHeader />
        <p className="panel empty-state">目录加载中…</p>
      </main>
    );
  }
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
    <main className={compareEntries.length > 0 ? "page catalog-page has-compare" : "page catalog-page"}>
      <CatalogHeader />
      <div className="catalog-layout">
        <section className="catalog-controls">
          <label className="search">
            <span className="visually-hidden">搜索</span>
            <input
              type="search"
              aria-label="搜索"
              placeholder="搜索耗材颜色、色号或品牌"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
            {searchText !== "" && (
              <button type="button" className="search-clear" onClick={() => setSearchText("")}>清空搜索</button>
            )}
          </label>
          <Filters
            brands={catalog.brands}
            families={[...FAMILIES].filter((family) => catalog.entries.some((entry) => entry.fam === family))}
            effects={effects}
            value={filters}
            onChange={setFilters}
          />
        </section>
        <div className="catalog-body">
          <div className="catalog-main">
            <SwatchGrid
              entries={entries}
              brands={catalog.brands}
              compareIds={compareIds}
              onSelect={setSelectedId}
              onCompare={addCompare}
              onUncompare={(id) => setCompareIds((current) => current.filter((item) => item !== id))}
            />
          </div>
          <aside className="catalog-rail" aria-label="色卡参数">
            <h2>色卡</h2>
            <p>共 {entries.length} 个颜色。点开一张色卡查看色值、渠道和相近色。</p>
            <p>{compareIds.length > 0 ? `对比托盘 ${compareIds.length}/4` : "还没有加入对比。"}</p>
          </aside>
        </div>
      </div>
      {brandOpen && (
        <div className="brand-sheet" role="dialog" aria-label="品牌">
          <div className="brand-sheet-head">
            <h2>品牌</h2>
            <button type="button" onClick={() => setBrandOpen(false)}>关闭</button>
          </div>
          <button type="button" onClick={() => { setFilters({ ...filters, brands: [] }); setBrandOpen(false); }}>全部品牌</button>
          {catalog.brands.map((brand) => (
            <button type="button" key={brand.slug} onClick={() => { setFilters({ ...filters, brands: [brand.slug] }); setBrandOpen(false); }}>
              {brand.name}
            </button>
          ))}
        </div>
      )}
      <nav className="fp-tabbar" aria-label="主导航">
        <a href="#/" aria-current={brandOpen ? undefined : "page"}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 4h7v7H4V4zm9 0h7v7h-7V4zM4 13h7v7H4v-7zm9 0h7v7h-7v-7z" /></svg>
          色卡
        </a>
        <button type="button" aria-pressed={brandOpen} className={filters.brands.length > 0 ? "is-on" : undefined} onClick={() => setBrandOpen(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 6h16v2H4V6zm2 5h12v2H6v-2zm3 5h6v2H9v-2z" /></svg>
          品牌
        </button>
        <a href="#compare-tray" className={compareIds.length > 0 ? "is-on" : undefined}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 4h4v16H7V4zm6 4h4v12h-4V8z" /></svg>
          对比{compareIds.length > 0 ? ` ${compareIds.length}` : ""}
        </a>
      </nav>
      {compareMessage && <p className="toast" role="status">{compareMessage}</p>}
      {compareEntries.length > 0 && (
        <CompareBar entries={compareEntries} onRemove={(id) => setCompareIds((current) => current.filter((item) => item !== id))} />
      )}
      {selected && (
        <ColorDetail
          entry={selected}
          catalog={catalog}
          onClose={() => setSelectedId(null)}
          onCompare={addCompare}
          onSelect={setSelectedId}
        />
      )}
    </main>
  );
}
