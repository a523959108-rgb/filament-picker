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

interface OriginalFile {
  available: boolean;
  reason: string | null;
  filename: string | null;
  size_bytes: number | null;
  sha256: string | null;
  media_type: string | null;
  url: string | null;
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
            <ModelCard model={model} navigate={navigate} key={model.id} />
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
  const [reload, setReload] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [activePlate, setActivePlate] = useState("");
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setModel(null);
    setError("");
    setUploadError("");
    fetch(`/api/models/${encodeURIComponent(id)}`, { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (!active) return;
        if (response.status === 401) { navigate("/models/login"); return; }
        if (response.status === 404) { setError("模型不存在"); return; }
        if (!response.ok) throw new Error();
        const result = await response.json() as Model;
        if (!active) return;
        setModel(result);
        const first = result.plates?.[0];
        setActivePlate(first ? plateKey(first, 0) : "");
      })
      .catch(() => { if (active) setError("模型加载失败，请重试"); });
    return () => { active = false; controller.abort(); };
  }, [id, navigate, reload]);
  if (error) return <p className="panel" role="alert">{error}</p>;
  if (model === null) return <p role="status">模型加载中…</p>;
  const loaded = model;
  const shots = orderedShots(loaded);
  const original = originalOf(loaded);
  const mesh = privateMeshUrl(loaded.mesh_url);
  async function onUpload(file: File | undefined) {
    if (!file) return;
    setUploadError("");
    const message = await uploadOriginal(loaded.id, file);
    if (message === "需要登录") { navigate("/models/login"); return; }
    if (message) { setUploadError(message); return; }
    setReload((value) => value + 1);
  }
  function selectPlate(key: string, plateNumber: number | null) {
    setActivePlate(key);
    if (plateNumber == null) return;
    document.getElementById(`model-shot-plate-${plateNumber}`)?.scrollIntoView?.({ block: "nearest" });
  }
  return (
    <article className="panel model-detail">
      <div className="model-shots">
        {mesh ? (
          <Suspense fallback={<p role="status">三维预览加载中…</p>}>
            <MeshViewer url={mesh} label={model.title} />
          </Suspense>
        ) : null}
        {shots.map((shot) => (
          <figure key={shot.url} className={shot.plate > 0 && activePlate === `plate-${shot.plate}` ? "is-active" : ""}>
            <img id={shot.kind === "plate" && shot.plate > 0 ? `model-shot-plate-${shot.plate}` : undefined}
              src={shot.url} alt={shotLabel(model.title, shot.kind, shot.plate)} />
            <figcaption>
              <span>{shotCaption(shot.kind, shot.plate)}</span>
              {shot.plate > 0 ? (
                <button type="button" onClick={() => selectPlate(`plate-${shot.plate}`, shot.plate)}>
                  对应盘 {shot.plate}
                </button>
              ) : null}
            </figcaption>
          </figure>
        ))}
      </div>
      <div>
        <h2>{model.title}</h2>
        <OriginalPanel
          model={model}
          original={original}
          navigate={navigate}
          uploadError={uploadError}
          onUpload={(file) => { void onUpload(file); }}
        />
        {model.description ? <p className="model-description">{model.description}</p> : null}
        <dl>
          <dt>系列</dt><dd>{model.series || "—"}</dd>
          <dt>作者</dt><dd>{model.author || "—"}</dd>
          <dt>盘数</dt><dd>{model.plate_count} 盘</dd>
          <dt>记录大小</dt><dd>{fileSize(model.size_bytes)}</dd>
        </dl>
        <PlateColours
          model={model}
          activePlate={activePlate}
          onSelect={selectPlate}
        />
      </div>
    </article>
  );
}

function ModelCard({ model, navigate }: { model: Model; navigate: Navigate }): JSX.Element {
  return (
    <article className="panel model-card">
      <a href={`/models/${encodeURIComponent(model.id)}`} aria-labelledby={`model-title-${model.id}`}>
        <img src={model.cover_url || model.thumb_url} alt={model.title} loading="lazy" />
        <h2 id={`model-title-${model.id}`}>{model.title}</h2>
      </a>
      <p>{model.series || "—"} / {model.author || "—"}</p>
      <DownloadControl original={originalOf(model)} title={model.title} navigate={navigate} />
    </article>
  );
}

function OriginalPanel({ model, original, navigate, uploadError, onUpload }: {
  model: Model;
  original: OriginalFile;
  navigate: Navigate;
  uploadError: string;
  onUpload: (file: File | undefined) => void;
}): JSX.Element {
  return (
    <section className="model-original" aria-label="原件下载">
      <DownloadControl original={original} title={model.title} navigate={navigate} />
      {original.available ? (
        <>
          <p>下载的是已入库原件 {original.filename}，不是预览图或三维网格。浏览器会核对字节数和校验和；没有亲自确认之前，不要删除本地备份。</p>
          {original.size_bytes != null ? <p>原件大小 {fileSize(original.size_bytes)}</p> : null}
          {original.sha256 ? <p className="model-checksum">校验和 <code>{original.sha256}</code></p> : null}
        </>
      ) : (
        <p>
          原件未入库。预览图和三维网格不能代替原始模型，也不能从它们恢复。
          {original.filename ? `记录的文件名：${original.filename}。文件本身不在服务器上。` : ""}
          请先保留本地备份。
        </p>
      )}
      <label className="model-upload">
        {original.available ? "更换原件" : "补存原件"}
        <input type="file" accept=".3mf,.stl" onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          onUpload(file);
        }} />
      </label>
      <p className="model-upload-note">只保存上传的 3MF 或 STL 原件，不会把预览图当成原件。</p>
      {uploadError ? <p role="alert">{uploadError}</p> : null}
    </section>
  );
}

function DownloadControl({ original, title, navigate }: {
  original: OriginalFile; title: string; navigate: Navigate;
}): JSX.Element {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function click() {
    if (busy) return;
    setBusy(true);
    setNote("");
    try {
      const message = await fetchOriginal(original, navigate);
      if (message) setNote(message);
    } finally {
      setBusy(false);
    }
  }
  const label = original.available
    ? `下载 ${title} 的原件${original.filename ? ` ${original.filename}` : ""}`
    : `${title} 的原件未入库，无法下载`;
  return (
    <div className="model-download-block">
      <button type="button" className="model-download" aria-label={label} disabled={busy}
        onClick={() => { void click(); }}>
        <DownloadIcon />
        <span>{busy ? "正在核对…" : original.available ? "下载原件" : "原件未入库"}</span>
      </button>
      {note ? <p role="alert">{note}</p> : null}
    </div>
  );
}

function DownloadIcon(): JSX.Element {
  return (
    <svg className="model-download-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 21h16" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PlateColours({ model, activePlate, onSelect }: {
  model: Model;
  activePlate: string;
  onSelect: (key: string, plateNumber: number | null) => void;
}): JSX.Element {
  const plates = model.plates;
  const matches = model.colour_matches ?? model.colours.map((hex) => ({ hex, picks: [] as ColourPick[] }));
  if (!Array.isArray(plates) || plates.length === 0) {
    const unknown = !Array.isArray(plates);
    return (
      <section aria-label="打印盘配色">
        <h3>打印盘配色</h3>
        <p>{unknown
          ? "这份预览没有保存盘和耗材的对应，不能判断哪一盘用什么颜色。"
          : "没有打印盘记录。"}
        </p>
        {matches.length > 0 ? (
          <>
            <h3>{unknown ? "原配色" : "未对应到盘的颜色"}</h3>
            <ColourList matches={matches} />
          </>
        ) : <p>没有配色数据。</p>}
      </section>
    );
  }
  return (
    <section aria-label="打印盘配色">
      <h3>打印盘配色</h3>
      <p className="model-plate-note">
        这里的盘是打印盘，槽位是耗材位置。编号用文字标出，不单靠颜色区分。部件没有单独的槽位记录，颜色属于这一整盘。
      </p>
      <div className="model-plates">
        {plates.map((plate, ordinal) => {
          const key = plateKey(plate, ordinal);
          const active = activePlate === key;
          return (
            <article className={active ? "model-plate is-active" : "model-plate"} id={`model-plate-${key}`} key={key}>
              <button type="button" className="model-plate-select" aria-pressed={active}
                onClick={() => onSelect(key, plate.index)}>
                <span className="model-plate-index">{plate.index == null ? "盘号未知" : `盘 ${plate.index}`}</span>
                <span>{plate.name || "未命名"}</span>
                {active ? <span className="model-plate-current">当前盘</span> : null}
              </button>
              <h4>部件</h4>
              {plate.objects.length > 0 ? (
                <ul className="model-objects">
                  {plate.objects.map((object, index) => <li key={`${object}-${index}`}>{object}</li>)}
                </ul>
              ) : <p>未记录部件</p>}
              <h4>本盘耗材</h4>
              {plate.filaments.length > 0 ? (
                <ul className="model-filaments">
                  {plate.filaments.map((filament, index) => (
                    <li key={`${filament.slot ?? "x"}-${filament.hex ?? "none"}-${index}`}>
                      <span className="model-slot-badge">耗材 {index + 1}</span>
                      <span className={filament.hex ? "model-colour" : "model-colour is-unknown"} role="img"
                        aria-label={swatchLabel(filament)} title={filament.hex ?? "颜色未知"}
                        style={filament.hex ? { backgroundColor: filament.hex } : undefined} />
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
            </article>
          );
        })}
      </div>
    </section>
  );
}

function ColourList({ matches }: { matches: ColourMatch[] }): JSX.Element {
  return (
    <div className="model-colours">
      {matches.map((match, index) => (
        <div className="model-colour-row" key={`${match.hex}-${index}`}>
          <span className="model-slot-badge">颜色 {index + 1}</span>
          <span className="model-colour" role="img" aria-label={match.hex} title={match.hex}
            style={{ backgroundColor: match.hex }} />
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

function swatchLabel(filament: PlateFilament): string {
  const slot = filament.slot == null ? "槽位未知" : `槽位 ${filament.slot}`;
  return filament.hex ? `${slot} 颜色 ${filament.hex}` : `${slot} 颜色未知`;
}

function originalOf(model: Model): OriginalFile {
  return model.original ?? {
    available: false,
    reason: "not_stored",
    filename: null,
    size_bytes: null,
    sha256: null,
    media_type: null,
    url: null,
  };
}

async function fetchOriginal(original: OriginalFile, navigate: Navigate): Promise<string> {
  if (!original.available || !original.url) {
    const recorded = original.filename ? `记录的文件名：${original.filename}。文件本身不在服务器上。` : "";
    return `原件未入库。预览图和三维网格不能代替原始模型，也不能从它们恢复。${recorded}请先保留本地备份。`;
  }
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
  const blob = new Blob([buffer], { type: original.media_type ?? "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = original.filename || "model.3mf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
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

async function uploadOriginal(id: string, file: File): Promise<string> {
  const body = new FormData();
  body.append("file", file, file.name);
  try {
    const response = await fetch(`/api/models/${encodeURIComponent(id)}/original`, {
      method: "POST", credentials: "same-origin", body,
    });
    if (response.status === 401) return "需要登录";
    if (!response.ok) return errorDetail(response);
    return "";
  } catch {
    return "连接失败，请稍后重试";
  }
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
