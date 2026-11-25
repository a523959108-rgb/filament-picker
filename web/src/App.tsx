import { useCallback, useEffect, useMemo, useState } from "react";
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
import { SiteHeader } from "./components/SiteHeader";
import { StackPage } from "./components/StackPage";
import { buildIndex, EMPTY_FILTER, hasActiveFilters, query } from "./search";
import type { FilterState } from "./search";
import type { WebCatalog } from "./types";

function routeFromHash(): string {
  return window.location.hash;
}

function pageFromHash(hash: string): "plan" | "cost" | "stack" | "photo" | "catalog" {
  const body = (hash.startsWith("#") ? hash.slice(1) : hash).split("?")[0] ?? "";
  const path = body.replace(/\/+$/, "") || "/";
  if (path === "/plan") return "plan";
  if (path === "/cost") return "cost";
  if (path === "/stack") return "stack";
  if (path === "/photo") return "photo";
  return "catalog";
}

function isModelsPath(pathname: string): boolean {
  return pathname === "/models" || pathname.startsWith("/models/");
}

function CatalogHeader(): JSX.Element {
  return (
    <SiteHeader
      page="catalog"
      title="耗材选色站"
      subtitle="按品牌、材料与色系浏览 3D 打印耗材颜色"
    />
  );
}

function PhotoHomeCta(): JSX.Element {
  return (
    <section className="stack-home-cta panel" aria-label="拍照找耗材入口">
      <div className="stack-home-cta-copy">
        <h2>拍照找耗材</h2>
        <p>上传实物或模型照片，提取主色，匹配最接近的可买耗材。照片不上传。</p>
      </div>
      <a className="stack-home-cta-btn" href="#/photo">
        开始找色
      </a>
    </section>
  );
}

function StackHomeCta(): JSX.Element {
  const href = stackEntryHref(window.location.hostname);
  const external = href.startsWith("http");
  return (
    <section className="stack-home-cta panel" aria-label="叠色入口">
      <div className="stack-home-cta-copy">
        <h2>四色叠色</h2>
        <p>上传图片，本机引擎生成叠色模型，并用色卡库推荐可买颜色。</p>
      </div>
      <a
        className="stack-home-cta-btn"
        href={href}
        {...(external ? { rel: "noopener noreferrer" } : {})}
      >
        打开叠色
      </a>
    </section>
  );
}

export default function App(): JSX.Element {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigateModels = useCallback((path: string) => {
    if (isModelsPath(path)) {
      window.history.pushState({}, "", path);
      setPathname(window.location.pathname);
      return;
    }
    window.location.assign(path);
  }, []);

  if (isModelsPath(pathname)) {
    return <ModelPreview path={pathname} navigate={navigateModels} />;
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
  const availableEffects = useMemo(() => {
    if (catalog === null) return [];
    const seen = new Set<string>();
    for (const entry of catalog.entries) {
      for (const effect of entry.eff) {
        if (effect) seen.add(effect);
      }
    }
    return [...seen].sort();
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
    <main className="page">
      <CatalogHeader />
      <div className="home-cta-row">
        <PhotoHomeCta />
        <StackHomeCta />
      </div>
      <div className="catalog-layout">
        <aside className="sidebar">
          <label className="search">
            <span className="field-label">搜索</span>
            <input
              type="search"
              aria-label="搜索"
              placeholder="颜色名、色号、拼音…"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>
          <Filters
            brands={catalog.brands}
            families={[...FAMILIES]}
            effects={availableEffects}
            value={filters}
            hasActive={hasActiveFilters(filters, searchText)}
            onReset={() => {
              setSearchText("");
              setFilters(EMPTY_FILTER);
            }}
            onChange={setFilters}
          />
        </aside>
        <div className="catalog-main">
          <SwatchGrid entries={entries} brands={catalog.brands} onSelect={setSelectedId} />
        </div>
      </div>
      {compareMessage && <p className="toast" role="status">{compareMessage}</p>}
      {compareEntries.length > 0 && (
        <CompareBar
          entries={compareEntries}
          brands={catalog.brands}
          onRemove={(id) => setCompareIds((current) => current.filter((item) => item !== id))}
          onClear={() => setCompareIds([])}
        />
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
