import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
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
  stock?: { in_stock?: boolean };
}

interface ColourMatch {
  hex: string;
  picks: ColourPick[];
}

interface PlateFilament {
  slot: number | null;
  hex: string | null;
  type: string;
  vendor: string;
  settings_id: string;
  used_g: number | null;
  picks?: ColourPick[];
}

interface PlateInfo {
  index: number | null;
  name: string | null;
  objects: string[];
  filaments: PlateFilament[];
}

interface OriginalFile {
  available: boolean;
  reason?: string | null;
  filename?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  media_type?: string | null;
  url?: string | null;
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
  plates?: PlateInfo[] | null;
  original?: OriginalFile | null;
}

interface ModelList {
  items: Model[];
  total: number;
  page: number;
  page_size: number;
  series: string[];
  authors: string[];
  materials?: string[];
}

type Navigate = (path: string) => void;
const goTo: Navigate = (path) => window.location.assign(path);

function Login({ navigate }: { navigate: Navigate }): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
    <section className="login-card">
      <p className="login-kicker">模型画廊与模型详情需要登录。耗材选色公开浏览。</p>
      <h2>工坊凭证登录</h2>
      <p className="login-lead">登录后进入模型画廊。账号由站方分配，不设开放注册。</p>
      <form onSubmit={submit}>
        <label>用户名<input name="username" autoComplete="username" placeholder="创作者工号" value={username}
          onChange={(event) => setUsername(event.target.value)} required /></label>
        <label>密码<input name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="访问凭证" value={password}
          onChange={(event) => setPassword(event.target.value)} required /></label>
        <div className="login-aux">
          <button type="button" onClick={() => setShowPassword((current) => !current)}>{showPassword ? "隐藏密码" : "显示密码"}</button>
          <button type="button" onClick={() => { setUsername(""); setPassword(""); }}>清空</button>
        </div>
        {error && <p role="alert">{error}</p>}
        <button className="login-submit" type="submit" disabled={busy}>{busy ? "登录中…" : "登录"}</button>
      </form>
    </section>
  );
}

const GALLERY_HREF_KEY = "fp.galleryHref";

interface GalleryParams {
  q: string; series: string; author: string; material: string;
  page: number; page_size: number; sort: string; order: string;
}

const PAGE_SIZES = [12, 24, 48] as const;
const SORTS: [string, string][] = [
  ["id", "编号"],
  ["created_at", "入库时间"],
  ["plate_count", "盘数"],
  ["colour_count", "颜色数"],
];

function galleryParamsFromLocation(): GalleryParams {
  const params = new URLSearchParams(window.location.search);
  const page = Number(params.get("page") || "1");
  const size = Number(params.get("page_size") || "12");
  const sort = params.get("sort") || "id";
  const order = params.get("order") || "asc";
  return {
    q: params.get("q") ?? "",
    series: params.get("series") ?? "",
    author: params.get("author") ?? "",
    material: params.get("material") ?? "",
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size: PAGE_SIZES.includes(size as 12 | 24 | 48) ? size : 12,
    sort: SORTS.some(([value]) => value === sort) ? sort : "id",
    order: order === "desc" ? "desc" : "asc",
  };
}

function toGalleryHref(params: GalleryParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.series) search.set("series", params.series);
  if (params.author) search.set("author", params.author);
  if (params.material) search.set("material", params.material);
  if (params.page > 1) search.set("page", String(params.page));
  if (params.page_size !== 12) search.set("page_size", String(params.page_size));
  if (params.sort !== "id") search.set("sort", params.sort);
  if (params.order !== "asc") search.set("order", params.order);
  const query = search.toString();
  return query ? `/models?${query}` : "/models";
}

function readStoredGalleryHref(): string {
  try {
    const value = sessionStorage.getItem(GALLERY_HREF_KEY);
    if (typeof value === "string" && (value === "/models" || value.startsWith("/models?"))) return value;
  } catch { /* sessionStorage can be blocked */ }
  return "/models";
}

function Gallery({ navigate, onHref }: { navigate: Navigate; onHref: (href: string) => void }): JSX.Element {
  const initial = galleryParamsFromLocation();
  const [data, setData] = useState<ModelList | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState(initial.q);
  const [params, setParams] = useState(initial);
  const href = toGalleryHref(params);
  useEffect(() => {
    onHref(href);
    try { sessionStorage.setItem(GALLERY_HREF_KEY, href); } catch { /* ignore */ }
    if (window.location.pathname === "/models" && `${window.location.pathname}${window.location.search}` !== href) {
      window.history.replaceState(null, "", href);
    }
  }, [href, onHref]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const query = new URLSearchParams({
      q: params.q,
      series: params.series,
      author: params.author,
      material: params.material,
      sort: params.sort,
      order: params.order,
      page: String(params.page),
      page_size: String(params.page_size),
    });
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

  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / params.page_size));
  const [jump, setJump] = useState("1");
  return (
    <>
      <form className="panel model-filters" onSubmit={(event) => {
        event.preventDefault(); setParams((current) => ({ ...current, q: search, page: 1 }));
      }}>
        <label>搜索模型<input type="search" value={search} placeholder="标题或编号"
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
        {(data?.materials?.length ?? 0) > 0 && (
          <label>材料<select value={params.material} onChange={(event) => {
            setParams((current) => ({ ...current, material: event.target.value, page: 1 }));
          }}><option value="">全部材料</option>
            {(data?.materials ?? []).map((value) => <option key={value} value={value}>{value}</option>)}
          </select></label>
        )}
        <label>排序<select value={params.sort} onChange={(event) => {
          setParams((current) => ({ ...current, sort: event.target.value, page: 1 }));
        }}>{SORTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>方向<select value={params.order} onChange={(event) => {
          setParams((current) => ({ ...current, order: event.target.value, page: 1 }));
        }}>
          <option value="asc">升序</option>
          <option value="desc">降序</option>
        </select></label>
        <button type="submit">搜索</button>
        <button type="button" onClick={() => {
          setSearch("");
          setParams({ q: "", series: "", author: "", material: "", page: 1, page_size: 12, sort: "id", order: "asc" });
        }}>清空筛选</button>
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
              <p className="model-card-by">{model.series || "—"} / {model.author || "—"}</p>
              <p className="model-card-meta">{model.plate_count} 盘 · {fileSize(model.size_bytes)}</p>
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
          <label>每页<select value={params.page_size} onChange={(event) => {
            setParams((current) => ({ ...current, page_size: Number(event.target.value), page: 1 }));
          }}>{PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
          </select></label>
          <form onSubmit={(event) => {
            event.preventDefault();
            const next = Number(jump);
            if (!Number.isInteger(next) || next < 1 || next > pageCount) return;
            setParams((current) => ({ ...current, page: next }));
          }}>
            <label>跳页<input inputMode="numeric" value={jump} onChange={(event) => setJump(event.target.value)} /></label>
            <button type="submit">前往</button>
          </form>
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
  const [activePlate, setActivePlate] = useState("");
  const [shotKind, setShotKind] = useState<"plate" | "top">("plate");
  const [descOpen, setDescOpen] = useState(false);
  const [locked, setLocked] = useState<{ hero: number; work: number } | null>(null);
  const screenRef = useRef<HTMLElement>(null);
  useEffect(() => {
    document.querySelector("main.model-preview")?.classList.toggle("is-desc-open", descOpen);
    return () => document.querySelector("main.model-preview")?.classList.remove("is-desc-open");
  }, [descOpen]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setModel(null);
    setError("");
    setActivePlate("");
    setShotKind("plate");
    setDescOpen(false);
    setLocked(null);
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
  const covers = coverShots(model);
  const cards = plateCards(model);
  const mesh = privateMeshUrl(model.mesh_url);
  const description = model.description ?? "";
  const longDescription = description.length > 160 || description.split("\n").length > 4;
  function selectPlate(key: string) {
    setActivePlate((current) => current === key ? "" : key);
    setShotKind("plate");
  }
  function toggleDescription() {
    const main = document.querySelector("main.model-preview");
    if (!descOpen) {
      const root = screenRef.current;
      const hero = root?.querySelector(".model-hero-pane")?.getBoundingClientRect().height ?? 0;
      const work = root?.querySelector(".model-work")?.getBoundingClientRect().height ?? 0;
      if (hero > 0 && work > 0) setLocked({ hero, work });
      main?.classList.add("is-desc-open");
      setDescOpen(true);
      return;
    }
    main?.classList.remove("is-desc-open");
    setLocked(null);
    setDescOpen(false);
  }
  const open = cards.find((card) => card.key === activePlate) ?? null;
  return (
    <article ref={screenRef} className="panel model-screen"
      style={locked ? {
        ["--hero-h" as string]: `${locked.hero}px`,
        ["--work-h" as string]: `${locked.work}px`,
      } : undefined}>
      <header className="model-head">
        <h2>{model.title}</h2>
        <p className="model-meta">
          <span>系列 {model.series || "—"}</span>
          <span>作者 {model.author || "—"}</span>
          <span>{model.plate_count} 盘</span>
          <span>{fileSize(model.size_bytes)}</span>
        </p>
        <DownloadControl model={model} navigate={navigate} />
        {description ? (
          <div className="model-description-block">
            <p className={longDescription && !descOpen ? "model-description is-clamped" : "model-description"}>{description}</p>
            {longDescription ? (
              <button type="button" className="model-text-button" aria-expanded={descOpen} onClick={toggleDescription}>
                {descOpen ? "收起说明" : "展开说明"}
              </button>
            ) : null}
          </div>
        ) : null}
      </header>
      <div className="model-stage">
        <div className="model-hero-pane">
          {covers.length > 0 ? covers.map((shot) => (
            <figure className="model-hero" key={shot.url}>
              <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
              <figcaption><span>{shotCaption(shot.kind, shot.plate)}</span></figcaption>
            </figure>
          )) : mesh ? null : <p className="model-hero-empty">没有封面</p>}
          {mesh ? (
            <Suspense fallback={<p role="status">三维预览加载中…</p>}>
              <MeshViewer url={mesh} label={model.title} />
            </Suspense>
          ) : null}
        </div>
        <PlateBoard cards={cards} model={model} active={open} shotKind={shotKind}
          onSelect={selectPlate} onShotKind={setShotKind} />
      </div>
      <ModelTools model={model} />
    </article>
  );
}

const PART_PREVIEW = 8;
const COMPARE_KEY = "fp.modelCompare";

interface DisplaySlot { plate_index: number; slot: number; hex: string }

function readCompare(): string[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(COMPARE_KEY) || "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string").slice(0, 3);
  } catch { return []; }
}

function ModelTools({ model }: { model: Model }): JSX.Element {
  const [slots, setSlots] = useState<DisplaySlot[]>([]);
  const [note, setNote] = useState("仅展示色，不修改原件，也不表示零件已换料");
  const [favorite, setFavorite] = useState(false);
  const [others, setOthers] = useState<Model[]>([]);
  const [message, setMessage] = useState("");
  const [schemeOpen, setSchemeOpen] = useState(false);
  const plates = Array.isArray(model.plates) ? model.plates : [];

  useEffect(() => {
    let active = true;
    const schemeRequest = fetch(`/api/models/${encodeURIComponent(model.id)}/scheme`, { credentials: "same-origin" });
    if (schemeRequest === undefined || typeof schemeRequest.then !== "function") return () => { active = false; };
    schemeRequest
      .then(async (response) => response?.ok ? response.json() as Promise<{ slots?: DisplaySlot[]; note?: string }> : null)
      .then((body) => {
        if (!active || body === null) return;
        setSlots(body.slots ?? []);
        if (body.note) setNote(body.note);
      })
      .catch(() => { if (active) setMessage("展示色加载失败"); });
    const favoriteRequest = fetch("/api/models/favorites", { credentials: "same-origin" });
    if (favoriteRequest && typeof favoriteRequest.then === "function") favoriteRequest
      .then(async (response) => response?.ok ? response.json() as Promise<{ items?: { model_id: string }[] }> : null)
      .then((body) => {
        if (active && body) setFavorite((body.items ?? []).some((item) => item.model_id === model.id));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [model.id]);

  useEffect(() => {
    const ids = readCompare().filter((item) => item !== model.id);
    let active = true;
    Promise.all(ids.map(async (item) => {
      const response = await fetch(`/api/models/${encodeURIComponent(item)}`, { credentials: "same-origin" });
      if (!response.ok) return null;
      return await response.json() as Model;
    })).then((rows) => { if (active) setOthers(rows.filter((row): row is Model => row !== null)); });
    return () => { active = false; };
  }, [model.id, message]);

  function displayHex(plateIndex: number | null, slot: number | null): string {
    if (plateIndex === null || slot === null) return "";
    return slots.find((item) => item.plate_index === plateIndex && item.slot === slot)?.hex ?? "";
  }

  async function saveScheme() {
    setMessage("");
    const response = await fetch(`/api/models/${encodeURIComponent(model.id)}/scheme`, {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slots }),
    });
    if (!response.ok) {
      setMessage("展示色没有保存");
      return;
    }
    const body = await response.json() as { note?: string; slots?: DisplaySlot[] };
    setSlots(body.slots ?? []);
    setMessage(body.note ?? "已保存展示色");
  }

  async function toggleFavorite() {
    const method = favorite ? "DELETE" : "PUT";
    const response = await fetch(`/api/models/favorites/${encodeURIComponent(model.id)}`, {
      method, credentials: "same-origin",
    });
    if (response.ok) setFavorite(!favorite);
    else setMessage("收藏没有保存");
  }

  function addCompare() {
    const next = [...new Set([model.id, ...readCompare()])].slice(0, 3);
    sessionStorage.setItem(COMPARE_KEY, JSON.stringify(next));
    setMessage("已加入模型对比。相同槽号不表示同一个零件。");
  }

  async function copyAddress() {
    const url = `${window.location.origin}/models/${encodeURIComponent(model.id)}`;
    try {
      await navigator.clipboard.writeText(url);
      setMessage("已复制站内地址，打开仍需登录");
    } catch {
      setMessage(url);
    }
  }

  const compared = [model, ...others.filter((item) => item.id !== model.id)];

  return (
    <section className="model-library">
      <div className="model-scheme-column">
      <div className="model-library-actions">
        <button type="button" onClick={() => { void toggleFavorite(); }}>{favorite ? "已收藏" : "收藏"}</button>
        <button type="button" onClick={addCompare}>加入模型对比</button>
        <button type="button" onClick={() => { void copyAddress(); }}>复制站内地址</button>
      </div>
      <p className="model-plate-note">{note}</p>
      <button type="button" aria-expanded={schemeOpen} onClick={() => setSchemeOpen((current) => !current)}>
        {schemeOpen ? "收起展示色" : "槽位展示色"}
      </button>
      {schemeOpen && plates.length === 0 ? <p>没有盘映射，不能保存展示色。</p> : null}
      {schemeOpen && plates.length > 0 ? (
        <div className="model-scheme">
          {plates.map((plate) => (
            <div key={plate.index ?? plate.name ?? "unknown"}>
              <p>{plate.index == null ? "盘号未知" : `盘 ${plate.index}`} 原色与展示色</p>
              {plate.filaments.map((filament, index) => (
                <label key={`${filament.slot ?? "x"}-${index}`}>
                  {filament.slot == null ? "槽位未知" : `槽位 ${filament.slot}`}
                  <span>原色 {filament.hex ?? "未知"}</span>
                  {filament.slot == null || plate.index == null ? <span>不能设置展示色</span> : (
                    <input aria-label={`盘 ${plate.index} 槽位 ${filament.slot} 展示色`} value={displayHex(plate.index, filament.slot)}
                      placeholder="#112233"
                      onChange={(event) => {
                        const hex = event.target.value;
                        setSlots((current) => {
                          const rest = current.filter((item) => item.plate_index !== plate.index || item.slot !== filament.slot);
                          if (!hex) return rest;
                          return [...rest, { plate_index: plate.index as number, slot: filament.slot as number, hex }];
                        });
                      }} />
                  )}
                </label>
              ))}
            </div>
          ))}
          <button type="button" onClick={() => { void saveScheme(); }}>保存展示色</button>
        </div>
      ) : null}
      </div>
      <div className="model-compare-column">
      {compared.length > 1 && (
        <div className="model-compare">
          <p>颜色差按色值计算，不是实测。不同模型的相同槽号不能当成同一个零件。</p>
          {compared.map((item) => (
            <article key={item.id}>
              <h3>{item.title}</h3>
              {(item.plates ?? []).map((plate) => (
                <p key={`${item.id}-${plate.index ?? "x"}`}>
                  {plate.index == null ? "盘号未知" : `盘 ${plate.index}`}
                  {plate.filaments.map((filament) => ` 槽位 ${filament.slot ?? "未知"} ${filament.hex ?? "未知"}`).join("；")}
                </p>
              ))}
            </article>
          ))}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      </div>
    </section>
  );
}


interface PlateCard {
  key: string;
  index: number | null;
  name: string | null;
  plate?: PlateInfo;
  face?: ModelImage;
  top?: ModelImage;
}

function PlateBoard({ cards, model, active, shotKind, onSelect, onShotKind, tools }: {
  cards: PlateCard[];
  model: Model;
  active: PlateCard | null;
  shotKind: "plate" | "top";
  onSelect: (key: string) => void;
  onShotKind: (kind: "plate" | "top") => void;
  tools?: JSX.Element;
}): JSX.Element {
  const [pickerOpen, setPickerOpen] = useState(true);
  const plates = model.plates;
  const matches = model.colour_matches ?? model.colours.map((hex) => ({ hex, picks: [] as ColourPick[] }));
  const known = Array.isArray(plates) && plates.length > 0;
  const note = known
    ? "颜色属于这一整盘，不是单个部件。"
    : plates === undefined || plates === null
      ? "这份预览没有保存盘和耗材的对应，不能判断哪一盘用什么颜色。"
      : "没有打印盘记录。";
  return (
    <section className="model-work" aria-label="打印盘配色">
      {tools}
      <div className="model-plate-tools">
        <p className="model-plate-note">{note}</p>
        {cards.length > 0 ? (
          <button type="button" className="model-text-button" aria-expanded={pickerOpen}
            onClick={() => setPickerOpen((current) => !current)}>
            {pickerOpen ? "收起盘列表" : `展开 ${cards.length} 盘`}
          </button>
        ) : null}
      </div>
      {cards.length > 0 && pickerOpen ? (
        <div className="model-plate-picker">
          {cards.map((card) => {
            const selected = active?.key === card.key;
            const thumb = card.face ?? card.top;
            const label = card.index == null ? "盘号未知" : `盘 ${card.index}`;
            return (
              <button type="button" key={card.key}
                className={selected ? "model-plate-card is-active" : "model-plate-card"}
                aria-pressed={selected}
                onClick={(event) => {
                  revealInPicker(event.currentTarget);
                  onSelect(card.key);
                }}>
                {thumb ? <img src={thumb.url} alt={shotLabel(model.title, thumb.kind, thumb.plate)} /> : <span className="model-plate-card-empty">无盘面图</span>}
                <span className="model-plate-card-index">{label}</span>
                {card.name ? <>{" "}<span className="model-plate-card-name" title={card.name}>{card.name}</span></> : null}
              </button>
            );
          })}
        </div>
      ) : null}
      {cards.length > 0 ? (
        <div className="model-plate-stage">
          {active ? (
            <PlateDetail model={model} card={active} shotKind={shotKind} onShotKind={onShotKind} />
          ) : <p className="model-plate-empty">点选上面的打印盘，查看盘面、部件和耗材。</p>}
        </div>
      ) : (
        <div className="model-tab-panel">
          {!known && matches.length > 0 ? (
            <>
              <h3>{plates === undefined || plates === null ? "原配色" : "未对应到盘的颜色"}</h3>
              <ColourList matches={matches} />
            </>
          ) : null}
          {!known && matches.length === 0 ? <p>没有配色数据。</p> : null}
        </div>
      )}
    </section>
  );
}

type PlateTab = "shot" | "parts" | "filaments";

function PlateDetail({ model, card, shotKind, onShotKind }: {
  model: Model;
  card: PlateCard;
  shotKind: "plate" | "top";
  onShotKind: (kind: "plate" | "top") => void;
}): JSX.Element {
  const [tab, setTab] = useState<PlateTab>("shot");
  const [showAllParts, setShowAllParts] = useState(false);
  useEffect(() => { setShowAllParts(false); }, [card.key]);
  const shot = shotKind === "top" && card.top ? card.top : (card.face ?? card.top);
  const plate = card.plate;
  const grouped = groupObjects(plate?.objects ?? []);
  const visible = showAllParts ? grouped : grouped.slice(0, PART_PREVIEW);
  const title = `${card.index == null ? "盘号未知" : `盘 ${card.index}`}${card.name ? ` ${card.name}` : ""}`;
  const tabs: { id: PlateTab; label: string }[] = [
    { id: "shot", label: "盘面" },
    { id: "parts", label: `部件 ${grouped.length}` },
    { id: "filaments", label: `耗材 ${plate?.filaments.length ?? 0}` },
  ];
  return (
    <div className="model-plate-detail" id="model-plate-detail">
      <div className="model-plate-detail-head">
        <p className="model-plate-current">{title || "当前盘"}</p>
        <p className="model-plate-summary">{grouped.length} 种部件 · {plate?.filaments.length ?? 0} 个耗材槽</p>
      </div>
      <div className="model-tabs" role="tablist" aria-label="当前盘内容">
        {tabs.map((item) => (
          <button type="button" key={item.id} role="tab" className="model-tab"
            aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="model-tab-panel" role="tabpanel">
        {tab === "shot" ? (
          <>
            {card.face && card.top ? <ViewToggle shotKind={shotKind} onShotKind={onShotKind} /> : null}
            {shot ? (
              <figure className="model-plate-preview">
                <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
                <figcaption><span>{shotCaption(shot.kind, shot.plate)}</span></figcaption>
              </figure>
            ) : <p>没有这一盘的图片。</p>}
            {!plate && (model.colour_matches?.length || model.colours.length) ? (
              <>
                <h3>原配色</h3>
                <ColourList matches={model.colour_matches ?? model.colours.map((hex) => ({ hex, picks: [] }))} />
              </>
            ) : null}
          </>
        ) : null}
        {tab === "parts" ? (
          grouped.length > 0 ? (
            <>
              <CompactShot model={model} card={card} shotKind={shotKind} />
              <ul className="model-objects">
                {visible.map((item) => (
                  <li key={item.name}>{item.count > 1 ? `${item.name} ×${item.count}` : item.name}</li>
                ))}
              </ul>
              {grouped.length > PART_PREVIEW ? (
                <button type="button" className="model-text-button" aria-expanded={showAllParts}
                  onClick={() => setShowAllParts((current) => !current)}>
                  {showAllParts ? "收起部件" : `查看全部 ${grouped.length} 种`}
                </button>
              ) : null}
            </>
          ) : <p>未记录部件</p>
        ) : null}
        {tab === "filaments" ? (
          <>
            <CompactShot model={model} card={card} shotKind={shotKind} />
            <FilamentList plate={plate} />
          </>
        ) : null}
      </div>
    </div>
  );
}

function ViewToggle({ shotKind, onShotKind }: {
  shotKind: "plate" | "top";
  onShotKind: (kind: "plate" | "top") => void;
}): JSX.Element {
  return (
    <div className="model-view-toggle" role="group" aria-label="视角">
      <button type="button" aria-pressed={shotKind !== "top"} onClick={() => onShotKind("plate")}>斜视</button>
      <button type="button" aria-pressed={shotKind === "top"} onClick={() => onShotKind("top")}>俯视</button>
    </div>
  );
}

function CompactShot({ model, card, shotKind }: {
  model: Model;
  card: PlateCard;
  shotKind: "plate" | "top";
}): JSX.Element | null {
  const shot = shotKind === "top" && card.top ? card.top : (card.face ?? card.top);
  if (!shot) return null;
  return (
    <figure className="model-plate-mini">
      <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
      <figcaption>{shotCaption(shot.kind, shot.plate)}</figcaption>
    </figure>
  );
}

function FilamentList({ plate }: { plate: PlateInfo | undefined }): JSX.Element {
  if (!plate) return <p>这一盘没有耗材映射。</p>;
  if (plate.filaments.length === 0) return <p>未记录耗材</p>;
  return (
    <ul className="model-filaments">
      {plate.filaments.map((filament, index) => (
        <li key={`${filament.slot ?? "x"}-${filament.hex ?? "none"}-${index}`}>
          <span className={filament.hex ? "model-colour" : "model-colour is-unknown"} role="img"
            aria-label={filament.hex ? `槽位 ${filament.slot ?? "未知"} 颜色 ${filament.hex}` : "槽位未知 颜色未知"}
            title={filament.hex ?? "颜色未知"}
            style={filament.hex ? { ["--swatch" as string]: filament.hex } : undefined} />
          <span>{filament.slot == null ? "槽位未知" : `槽位 ${filament.slot}`}</span>
          <span>{filament.hex ?? "颜色未知"}</span>
          {filament.type ? <span>{filament.type}</span> : null}
          {filament.vendor ? <span>{filament.vendor}</span> : null}
          {filament.used_g != null ? <span>{`${filament.used_g} g`}</span> : null}
          {filament.settings_id ? <span className="model-colour-match">{filament.settings_id}</span> : null}
          {filament.picks?.[0] ? (
            <span className="model-colour-match">
              {filament.picks[0].brand_name} {filament.picks[0].name}
              {filament.picks[0].label ? ` · ${filament.picks[0].label}` : ""}
              {filament.picks[0].stock?.in_stock === true ? " · 库存有" : ""}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ColourList({ matches }: { matches: ColourMatch[] }): JSX.Element {
  return (
    <div className="model-colours">
      {matches.map((match, index) => (
        <div className="model-colour-row" key={`${match.hex}-${index}`}>
          <span className="model-slot-badge">颜色 {index + 1}</span>
          <span className="model-colour" role="img" aria-label={match.hex} title={match.hex}
            style={{ ["--swatch" as string]: match.hex }} />
          <span>{match.hex}</span>
          {match.picks[0] ? (
            <span className="model-colour-match">
              {match.picks[0].brand_name} {match.picks[0].name}
              {match.picks[0].label ? ` · ${match.picks[0].label}` : ""}
              {match.picks[0].stock?.in_stock === true ? " · 库存有" : ""}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function plateKey(plate: PlateInfo, ordinal: number): string {
  return plate.index == null ? `unknown-${ordinal}` : `plate-${plate.index}`;
}

function coverShots(model: Model): ModelImage[] {
  const images = model.images ?? [];
  const covers = images.filter((image) => image.kind === "cover");
  if (covers.length > 0) return covers;
  if (model.cover_url) return [{ kind: "cover", plate: 0, url: model.cover_url }];
  return [];
}

function plateCards(model: Model): PlateCard[] {
  const images = model.images ?? [];
  const faceOf = (plate: number) => images.find((image) => image.kind === "plate" && image.plate === plate);
  const topOf = (plate: number) => images.find((image) => image.kind === "top" && image.plate === plate);
  if (Array.isArray(model.plates) && model.plates.length > 0) {
    return model.plates.map((plate, ordinal) => ({
      key: plateKey(plate, ordinal),
      index: plate.index,
      name: plate.name,
      plate,
      face: plate.index == null ? undefined : faceOf(plate.index),
      top: plate.index == null ? undefined : topOf(plate.index),
    }));
  }
  const numbers = [...new Set(images.filter((image) => image.plate > 0).map((image) => image.plate))]
    .sort((left, right) => left - right);
  return numbers.map((plate) => ({
    key: `plate-${plate}`,
    index: plate,
    name: null,
    face: faceOf(plate),
    top: topOf(plate),
  }));
}

function groupObjects(names: string[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);
  return [...counts.entries()].map(([name, count]) => ({ name, count }));
}

function privateMeshUrl(url: string | null | undefined): string | null {
  if (url == null || !PRIVATE_MESH.test(url)) return null;
  return url;
}

function shotCaption(kind: ModelImage["kind"], plate: number): string {
  if (kind === "cover") return "封面";
  return kind === "top" ? `俯视 ${plate}` : `斜视 ${plate}`;
}

function shotLabel(title: string, kind: ModelImage["kind"], plate: number): string {
  return `${title} ${shotCaption(kind, plate)}`;
}

const DOWNLOAD_IDLE = "未接通，暂不能下载";

function canDownload(model: Model): OriginalFile | null {
  const original = model.original;
  if (!original?.available || typeof original.url !== "string") return null;
  if (!original.url.startsWith("/api/models/")) return null;
  return original;
}

function revealInPicker(target: HTMLElement): void {
  const scroller = target.closest(".model-plate-picker");
  if (!(scroller instanceof HTMLElement)) return;
  const top = target.offsetTop - scroller.offsetTop;
  const bottom = top + target.offsetHeight;
  if (top < scroller.scrollTop) scroller.scrollTop = top;
  else if (bottom > scroller.scrollTop + scroller.clientHeight) {
    scroller.scrollTop = bottom - scroller.clientHeight;
  }
}

function DownloadControl({ model, navigate }: { model: Model; navigate: Navigate }): JSX.Element {
  const original = canDownload(model);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function click() {
    if (!original || busy) return;
    setBusy(true);
    setNote("");
    try {
      const message = await fetchOriginal(original, navigate);
      if (message) setNote(message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="model-download-block">
      <button type="button" className="model-download" disabled={original == null || busy}
        aria-disabled={original == null || busy} aria-describedby="model-download-status"
        onClick={() => { void click(); }}>
        {busy ? "正在核对…" : "下载3MF"}
      </button>
      <p id="model-download-status" className="model-download-status">
        {original ? (original.filename || "可下载已入库原件") : DOWNLOAD_IDLE}
      </p>
      {note ? <p role="alert">{note}</p> : null}
    </div>
  );
}

async function fetchOriginal(original: OriginalFile, navigate: Navigate): Promise<string> {
  if (!original.available || !original.url?.startsWith("/api/models/")) return DOWNLOAD_IDLE;
  let response: Response;
  try {
    response = await fetch(original.url, { credentials: "same-origin" });
  } catch {
    return "下载失败，请重试";
  }
  if (response.status === 401) {
    navigate("/models/login");
    return "";
  }
  if (!response.ok) return errorDetail(response);
  const buffer = await response.arrayBuffer();
  if (original.size_bytes != null && buffer.byteLength !== original.size_bytes) {
    return "下载的字节数和记录不一致，已取消保存。";
  }
  if (original.sha256) {
    const actual = await sha256Hex(buffer);
    const header = response.headers.get("X-Content-SHA256");
    if (actual == null || actual !== original.sha256 || (header != null && header !== original.sha256)) {
      return "下载校验和不匹配，已取消保存。";
    }
  }
  try {
    const blob = new Blob([buffer], { type: original.media_type ?? "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = original.filename || "model.3mf";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch {
    return "下载失败，请重试";
  }
  return "";
}

async function sha256Hex(buffer: ArrayBuffer): Promise<string | null> {
  if (!globalThis.crypto?.subtle) return null;
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    return "下载失败，请重试";
  }
  return "下载失败，请重试";
}

export function ModelPreview({ path = window.location.pathname, navigate = goTo }: {
  path?: string; navigate?: Navigate;
}): JSX.Element {
  const normalized = path.replace(/\/+$/, "");
  const login = normalized === "/models/login";
  const detailView = !login && normalized !== "/models";
  const [error, setError] = useState("");
  const [galleryHref, setGalleryHref] = useState(readStoredGalleryHref);
  const rememberGallery = useCallback((href: string) => setGalleryHref(href), []);
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
    <main className={detailView ? "page model-preview is-detail" : "page model-preview"}>
      <header className="topbar">
        <h1>{login ? "登录" : detailView ? "模型详情" : "模型画廊"}</h1>
        <nav className="topbar-nav" aria-label="页面导航">
          <a className="nav-link" href="/">耗材选色</a>
          {detailView && <a className="nav-link model-back" href={galleryHref}>返回画廊</a>}
          {!login && <button onClick={logout}>退出登录</button>}
        </nav>
      </header>
      <p className="model-banner" role="note">仅私人收藏预览、禁止外传</p>
      {error && <p role="alert">{error}</p>}
      {login ? <Login navigate={navigate} /> : normalized === "/models" ? <Gallery navigate={navigate} onHref={rememberGallery} /> : (
        <Detail id={id} navigate={navigate} />
      )}
    </main>
  );
}
