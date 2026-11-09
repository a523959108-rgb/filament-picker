import { lazy, Suspense, useEffect, useState } from "react";
import type { FormEvent, JSX } from "react";
import "./model-preview.css";

const MeshViewer = lazy(() =>
  import("./MeshViewer").then((module) => ({ default: module.MeshViewer })),
);
const PRIVATE_MESH = /^\/api\/models\/[A-Za-z0-9_-]{1,128}\/glb$/;

interface ModelImage {
  kind: "cover" | "plate" | "top";
  plate: number;
  url: string;
}

interface ColourPick {
  id: string;
  name: string;
  brand_name: string;
  series_name: string;
  hex: string;
  delta_e: number;
  label: string | null;
}

interface ColourMatch {
  hex: string;
  picks: ColourPick[];
}

interface Model {
  id: string;
  title: string;
  series: string;
  author: string;
  size_bytes: number;
  plate_count: number;
  colours: string[];
  thumb_url: string;
  cover_url?: string | null;
  created_at: string;
  description?: string;
  images?: ModelImage[];
  colour_matches?: ColourMatch[];
  mesh_url?: string | null;
}

interface ModelList {
  items: Model[];
  total: number;
  page: number;
  page_size: number;
  series: string[];
  authors: string[];
}

type Navigate = (path: string) => void;
const goTo: Navigate = (path) => window.location.assign(path);

function Login({ navigate }: { navigate: Navigate }): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/models/login", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (response.ok) navigate("/models");
      else if (response.status === 429) setError("登录尝试过多，请稍后重试");
      else if (response.status === 401) setError("用户名或密码错误");
      else setError("暂时无法登录，请稍后重试");
    } catch {
      setError("连接失败，请稍后重试");
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <section className="panel model-login">
      <h2>登录模型预览</h2>
      <form onSubmit={submit}>
        <label>用户名<input name="username" autoComplete="username" value={username}
          onChange={(event) => setUsername(event.target.value)} required /></label>
        <label>密码<input name="password" type="password" autoComplete="current-password" value={password}
          onChange={(event) => setPassword(event.target.value)} required /></label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "登录中…" : "登录"}</button>
      </form>
    </section>
  );
}

function Gallery({ navigate }: { navigate: Navigate }): JSX.Element {
  const [data, setData] = useState<ModelList | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [params, setParams] = useState({ q: "", series: "", author: "", page: 1 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ ...params, page: String(params.page), page_size: "12" });
    fetch(`/api/models?${query}`, { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (!active) return;
        if (response.status === 401) { navigate("/models/login"); return; }
        if (!response.ok) throw new Error();
        const result = await response.json() as ModelList;
        if (active) setData(result);
      })
      .catch(() => { if (active) setError("模型加载失败，请重试"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [params, navigate]);

  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / 12));
  return (
    <>
      <form className="panel model-filters" onSubmit={(event) => {
        event.preventDefault(); setParams((current) => ({ ...current, q: search, page: 1 }));
      }}>
        <label>搜索模型<input type="search" value={search} placeholder="按标题搜索"
          onChange={(event) => setSearch(event.target.value)} /></label>
        <label>系列<select value={params.series} onChange={(event) => {
          setParams((current) => ({ ...current, series: event.target.value, page: 1 }));
        }}><option value="">全部系列</option>
          {data?.series.map((value) => <option key={value} value={value}>{value}</option>)}
        </select></label>
        <label>作者<select value={params.author} onChange={(event) => {
          setParams((current) => ({ ...current, author: event.target.value, page: 1 }));
        }}><option value="">全部作者</option>
          {data?.authors.map((value) => <option key={value} value={value}>{value}</option>)}
        </select></label>
        <button type="submit">搜索</button>
      </form>
      {error && <p className="panel" role="alert">{error}</p>}
      {loading && <p role="status">模型加载中…</p>}
      {data && !error && <>
        <p className="model-count">共 {data.total} 个模型</p>
        {data.items.length === 0 && <p className="panel">没有找到模型</p>}
        <div className="model-grid" aria-busy={loading}>
          {data.items.map((model) => (
            <article className="panel model-card" key={model.id}>
              <a href={`/models/${encodeURIComponent(model.id)}`} aria-labelledby={`model-title-${model.id}`}>
                <img src={model.cover_url || model.thumb_url} alt={model.title} loading="lazy" />
                <h2 id={`model-title-${model.id}`}>{model.title}</h2>
              </a>
              <p>{model.series || "—"} / {model.author || "—"}</p>
            </article>
          ))}
        </div>
        <nav className="model-pagination" aria-label="模型分页">
          <button disabled={loading || params.page <= 1} onClick={() => {
            setParams((current) => ({ ...current, page: current.page - 1 }));
          }}>上一页</button>
          <span>第 {params.page} / {pageCount} 页</span>
          <button disabled={loading || params.page >= pageCount} onClick={() => {
            setParams((current) => ({ ...current, page: current.page + 1 }));
          }}>下一页</button>
        </nav>
      </>}
    </>
  );
}

function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function Detail({ id, navigate }: { id: string; navigate: Navigate }): JSX.Element {
  const [model, setModel] = useState<Model | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setModel(null);
    setError("");
    fetch(`/api/models/${encodeURIComponent(id)}`, { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (!active) return;
        if (response.status === 401) { navigate("/models/login"); return; }
        if (response.status === 404) { setError("模型不存在"); return; }
        if (!response.ok) throw new Error();
        const result = await response.json() as Model;
        if (active) setModel(result);
      })
      .catch(() => { if (active) setError("模型加载失败，请重试"); });
    return () => { active = false; controller.abort(); };
  }, [id, navigate]);
  if (error) return <p className="panel" role="alert">{error}</p>;
  if (model === null) return <p role="status">模型加载中…</p>;
  const shots = orderedShots(model);
  const matches = model.colour_matches ?? model.colours.map((hex) => ({ hex, picks: [] }));
  const mesh = privateMeshUrl(model.mesh_url);
  return (
    <article className="panel model-detail">
      <div className="model-shots">
        {mesh ? (
          <Suspense fallback={<p role="status">三维预览加载中…</p>}>
            <MeshViewer url={mesh} label={model.title} />
          </Suspense>
        ) : null}
        {shots.map((shot) => (
          <figure key={shot.url}>
            <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
            <figcaption>{shotCaption(shot.kind, shot.plate)}</figcaption>
          </figure>
        ))}
      </div>
      <div>
        <h2>{model.title}</h2>
        {model.description ? <p className="model-description">{model.description}</p> : null}
        <dl>
          <dt>系列</dt><dd>{model.series || "—"}</dd>
          <dt>作者</dt><dd>{model.author || "—"}</dd>
          <dt>盘数</dt><dd>{model.plate_count} 盘</dd>
          <dt>大小</dt><dd>{fileSize(model.size_bytes)}</dd>
        </dl>
        <h3>原配色</h3>
        <div className="model-colours">
          {matches.map((match, index) => (
            <div className="model-colour-row" key={`${match.hex}-${index}`}>
              <span className="model-colour" role="img" aria-label={match.hex} title={match.hex}
                style={{ backgroundColor: match.hex }} />
              {match.picks[0] ? (
                <span className="model-colour-match">
                  {match.picks[0].brand_name} {match.picks[0].name}
                  {match.picks[0].label ? ` · ${match.picks[0].label}` : ""}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function privateMeshUrl(url: string | null | undefined): string | null {
  if (url == null || !PRIVATE_MESH.test(url)) return null;
  return url;
}

function orderedShots(model: Model): ModelImage[] {
  const images = model.images ?? [];
  const cover = images.filter((image) => image.kind === "cover");
  const rest = images.filter((image) => image.kind !== "cover");
  if (cover.length + rest.length > 0) return [...cover, ...rest];
  if (model.cover_url) return [{ kind: "cover", plate: 0, url: model.cover_url }];
  return [{ kind: "plate", plate: 1, url: model.thumb_url }];
}

function shotCaption(kind: ModelImage["kind"], plate: number): string {
  if (kind === "cover") return "封面";
  return kind === "top" ? `俯视 ${plate}` : `盘面 ${plate}`;
}

function shotLabel(title: string, kind: ModelImage["kind"], plate: number): string {
  return `${title} ${shotCaption(kind, plate)}`;
}

export function ModelPreview({ path = window.location.pathname, navigate = goTo }: {
  path?: string; navigate?: Navigate;
}): JSX.Element {
  const normalized = path.replace(/\/+$/, "");
  const login = normalized === "/models/login";
  const [error, setError] = useState("");
  async function logout() {
    setError("");
    try {
      const response = await fetch("/api/models/logout", { method: "POST", credentials: "same-origin" });
      if (response.ok || response.status === 401) navigate("/models/login");
      else setError("退出失败，请重试");
    } catch { setError("连接失败，请稍后重试"); }
  }
  let id = "";
  try { id = decodeURIComponent(normalized.slice("/models/".length)); }
  catch { id = ""; }
  return (
    <main className="page model-preview">
      <header className="topbar">
        <h1>模型预览</h1>
        <nav className="topbar-nav" aria-label="页面导航">
          <a className="nav-link" href="/">耗材选色</a>
          {!login && <>
            <a className="nav-link" href="/models">模型画廊</a>
            <button onClick={logout}>退出登录</button>
          </>}
        </nav>
      </header>
      <p className="model-banner" role="note">仅私人收藏预览、禁止外传</p>
      {error && <p role="alert">{error}</p>}
      {login ? <Login navigate={navigate} /> : normalized === "/models" ? <Gallery navigate={navigate} /> : (
        <Detail id={id} navigate={navigate} />
      )}
    </main>
  );
}
