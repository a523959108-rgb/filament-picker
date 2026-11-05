import { useEffect, useState } from "react";
import type { JSX } from "react";
import { loadCatalog } from "./catalog";
import { SwatchGrid } from "./components/SwatchGrid";
import type { WebCatalog } from "./types";

function routeFromHash(): string {
  return window.location.hash;
}

export default function App(): JSX.Element {
  const [route, setRoute] = useState(routeFromHash);
  const [catalog, setCatalog] = useState<WebCatalog | null>(null);
  const [loadError, setLoadError] = useState(false);

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

  if (route === "#/plan") {
    return <main className="page"><p>图片配色（T24）</p></main>;
  }
  if (loadError) {
    return <main className="page"><p>目录加载失败</p></main>;
  }
  if (catalog === null) {
    return <main className="page"><p>目录加载中…</p></main>;
  }
  return (
    <main className="page">
      <h1>耗材选色站</h1>
      <SwatchGrid entries={catalog.entries} brands={catalog.brands} />
    </main>
  );
}
