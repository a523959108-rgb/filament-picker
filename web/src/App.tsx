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
import { StackPage } from "./components/StackPage";
import { buildIndex, EMPTY_FILTER, query } from "./search";
import type { FilterState } from "./search";
import type { WebCatalog } from "./types";

function routeFromHash(): string {
  return window.location.hash;
}

function CatalogHeader(): JSX.Element {
  const stackHref = stackEntryHref(window.location.hostname);
  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1>耗材选色站</h1>
        <p className="topbar-sub">按品牌、材料与色系浏览 3D 打印耗材颜色</p>
      </div>
      <nav className="topbar-nav" aria-label="页面导航">
        <a href="#/plan" className="nav-link">图片配色</a>
        <a href="#/cost" className="nav-link">打印成本</a>
        <a href={stackHref} className="nav-link">叠色</a>
        <a href="/models/login" className="nav-link">模型预览</a>
      </nav>
    </header>
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
  if (window.location.pathname === "/models" || window.location.pathname.startsWith("/models/")) {
    return <ModelPreview />;
  }
  return <CatalogApp />;
}

function CatalogApp(): JSX.Element {
  const [route, setRoute] = useState(
    () => defaultStackHash(window.location.hostname, routeFromHash()) ?? routeFromHash(),
  );
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
    if (route === "#/plan" || route === "#/stack") return;
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
  const entries = useMemo(
    () =>
      catalog === null || index === null
        ? []
        : query(index, catalog, searchText, filters),
    [index, catalog, searchText, filters],
  );

  if (route === "#/plan") {
    return <main className="page"><PlanPage /></main>;
  }
  if (route === "#/cost") {
    return <main className="page"><CostPage /></main>;
  }
  if (route === "#/stack") {
    return <StackPage />;
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
      <StackHomeCta />
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
          <Filters brands={catalog.brands} families={[...FAMILIES]} value={filters} onChange={setFilters} />
        </aside>
        <div className="catalog-main">
          <SwatchGrid entries={entries} brands={catalog.brands} onSelect={setSelectedId} />
        </div>
      </div>
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
