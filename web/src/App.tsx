import { useEffect, useMemo, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "./catalog";
import { FAMILIES, defaultStackHash, stackEntryHref } from "./config";
import { Filters } from "./components/Filters";
import { ColorDetail } from "./components/ColorDetail";
import { CompareBar } from "./components/CompareBar";
import { SwatchGrid } from "./components/SwatchGrid";
import { PlanPage } from "./components/PlanPage";
import { CostPage } from "./components/CostPage";
import { ModelPreview } from "./components/ModelPreview";
import { PhotoPage } from "./components/PhotoPage";
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
  return (
    <header className="topbar catalog-top">
      <div className="topbar-title">
        <span className="brand-mark" aria-hidden="true" />
        <h1>耗材选色</h1>
      </div>
      <nav className="topbar-nav" aria-label="页面导航">
        <a href="/models" className="nav-link">画廊</a>
        <a href="/models/login" className="nav-link">登录</a>
      </nav>
    </header>
  );
}

function CatalogTools(): JSX.Element {
  const stackHref = stackEntryHref(window.location.hostname);
  return (
    <nav className="fp-tabbar" aria-label="工具">
      <a className="nav-link" href="#/photo">拍照找耗材</a>
      <a className="nav-link fp-alias" href="#/photo">开始找色</a>
      <a className="nav-link" href="#/plan">图片配色</a>
      <a className="nav-link" href="#/cost">打印成本</a>
      <a className="nav-link" href={stackHref}>叠色</a>
      <a className="nav-link fp-alias" href={stackHref}>打开叠色</a>
      <a className="nav-link" href="#/specs">规格索引</a>
    </nav>
  );
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
    <main className="page catalog-page">
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
      </div>
      <CatalogTools />
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
