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
  const [activePlate, setActivePlate] = useState("");
  const [shotKind, setShotKind] = useState<"plate" | "top">("plate");
  const [descOpen, setDescOpen] = useState(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setModel(null);
    setError("");
    setActivePlate("");
    setShotKind("plate");
    setDescOpen(false);
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
  const open = cards.find((card) => card.key === activePlate) ?? null;
  return (
    <article className="panel model-detail">
      <div className={covers.length > 0 ? "model-summary" : "model-summary no-cover"}>
        {covers.length > 0 ? (
          <div className="model-shots">
            {covers.map((shot) => (
              <figure className="model-hero" key={shot.url}>
                <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
                <figcaption><span>{shotCaption(shot.kind, shot.plate)}</span></figcaption>
              </figure>
            ))}
          </div>
        ) : null}
        <div className="model-summary-copy">
          <h2>{model.title}</h2>
          <p className="model-meta">
            <span>系列 {model.series || "—"}</span>
            <span>作者 {model.author || "—"}</span>
            <span>{model.plate_count} 盘</span>
            <span>{fileSize(model.size_bytes)}</span>
          </p>
          {description ? (
            <>
              <p className={longDescription && !descOpen ? "model-description is-clamped" : "model-description"}>{description}</p>
              {longDescription ? (
                <button type="button" className="model-text-button" aria-expanded={descOpen}
                  onClick={() => setDescOpen((current) => !current)}>
                  {descOpen ? "收起说明" : "展开说明"}
                </button>
              ) : null}
            </>
          ) : null}
          {mesh ? (
            <Suspense fallback={<p role="status">三维预览加载中…</p>}>
              <MeshViewer url={mesh} label={model.title} />
            </Suspense>
          ) : null}
        </div>
      </div>
      <PlateBoard cards={cards} model={model} active={open} shotKind={shotKind}
        onSelect={selectPlate} onShotKind={setShotKind} />
    </article>
  );
}

const PART_PREVIEW = 8;

interface PlateCard {
  key: string;
  index: number | null;
  name: string | null;
  plate?: PlateInfo;
  face?: ModelImage;
  top?: ModelImage;
}

function PlateBoard({ cards, model, active, shotKind, onSelect, onShotKind }: {
  cards: PlateCard[];
  model: Model;
  active: PlateCard | null;
  shotKind: "plate" | "top";
  onSelect: (key: string) => void;
  onShotKind: (kind: "plate" | "top") => void;
}): JSX.Element {
  const plates = model.plates;
  const matches = model.colour_matches ?? model.colours.map((hex) => ({ hex, picks: [] as ColourPick[] }));
  const known = Array.isArray(plates) && plates.length > 0;
  return (
    <section aria-label="打印盘配色">
      <div className={cards.length > 0 ? "model-plate-layout" : undefined}>
        <div>
          <h3>打印盘</h3>
          <p className="model-plate-note">
            {known
              ? "点一盘查看部件和耗材。盘是打印盘，槽位是耗材位置。颜色属于这一整盘，没有逐个部件的分色。"
              : plates === undefined || plates === null
                ? "这份预览没有保存盘和耗材的对应，不能判断哪一盘用什么颜色。"
                : "没有打印盘记录。"}
          </p>
          {cards.length > 0 ? (
            <div className="model-plate-picker">
              {cards.map((card) => {
                const selected = active?.key === card.key;
                const thumb = card.face ?? card.top;
                const label = card.index == null ? "盘号未知" : `盘 ${card.index}`;
                return (
                  <button type="button" key={card.key}
                    className={selected ? "model-plate-card is-active" : "model-plate-card"}
                    aria-pressed={selected}
                    onClick={() => onSelect(card.key)}>
                    {thumb ? <img src={thumb.url} alt={shotLabel(model.title, thumb.kind, thumb.plate)} /> : <span className="model-plate-card-empty">无盘面图</span>}
                    <span className="model-plate-card-name">{label}{card.name ? ` ${card.name}` : ""}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        {cards.length > 0 ? (
          <div className="model-plate-detail-slot">
            {active ? <PlateDetail model={model} card={active} shotKind={shotKind} onShotKind={onShotKind} /> : <p>尚未展开打印盘。</p>}
          </div>
        ) : null}
      </div>
      {!known && matches.length > 0 ? (
        <>
          <h3>{plates === undefined || plates === null ? "原配色" : "未对应到盘的颜色"}</h3>
          <ColourList matches={matches} />
        </>
      ) : null}
      {!known && matches.length === 0 && cards.length === 0 ? <p>没有配色数据。</p> : null}
    </section>
  );
}

function PlateDetail({ model, card, shotKind, onShotKind }: {
  model: Model;
  card: PlateCard;
  shotKind: "plate" | "top";
  onShotKind: (kind: "plate" | "top") => void;
}): JSX.Element {
  const [showAllParts, setShowAllParts] = useState(false);
  const shot = shotKind === "top" && card.top ? card.top : (card.face ?? card.top);
  const plate = card.plate;
  const grouped = groupObjects(plate?.objects ?? []);
  const visible = showAllParts ? grouped : grouped.slice(0, PART_PREVIEW);
  const title = `${card.index == null ? "盘号未知" : `盘 ${card.index}`}${card.name ? ` ${card.name}` : " 未命名"}`;
  return (
    <div className="model-plate-detail" id="model-plate-detail">
      <div className="model-plate-detail-head">
        <p className="model-plate-current">{title}</p>
        {card.face && card.top ? (
          <div className="model-view-toggle" role="group" aria-label="盘面视图">
            <button type="button" aria-pressed={shotKind !== "top"} onClick={() => onShotKind("plate")}>盘面</button>
            <button type="button" aria-pressed={shotKind === "top"} onClick={() => onShotKind("top")}>俯视</button>
          </div>
        ) : null}
      </div>
      {shot ? (
        <figure className="model-plate-preview">
          <img src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
          <figcaption><span>{shotCaption(shot.kind, shot.plate)}</span></figcaption>
        </figure>
      ) : null}
      {plate ? (
        <>
          <h4>部件</h4>
          {grouped.length > 0 ? (
            <>
              <ul className={showAllParts ? "model-objects is-open" : "model-objects"}>
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
          ) : <p>未记录部件</p>}
          <h4>本盘耗材</h4>
          {plate.filaments.length > 0 ? (
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
          ) : <p>未记录耗材</p>}
        </>
      ) : <p>这一盘没有耗材映射。</p>}
    </div>
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
