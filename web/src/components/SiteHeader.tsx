import { useEffect, useRef, useState } from "react";
import type { JSX, MouseEvent } from "react";
import { stackEntryHref } from "../config";
import { applyTheme, nextThemeBoundary, readThemeMode, writeThemeMode } from "../theme";
import type { ThemeMode } from "../theme";

const PAGE_NAME = {
  catalog: "耗材选色",
  gallery: "模型画廊",
  detail: "模型详情",
  login: "登录",
} as const;

const THEME_LABEL: Record<ThemeMode, string> = {
  auto: "自动",
  light: "亮色",
  dark: "暗色",
};

function ThemeIcon({ mode, size = 18 }: { mode: ThemeMode; size?: number }): JSX.Element {
  if (mode === "light") {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
    );
  }
  if (mode === "dark") {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function useThemeClock(): void {
  useEffect(() => {
    let timer = 0;
    const refresh = () => {
      applyTheme(readThemeMode());
      window.dispatchEvent(new Event("fp-theme"));
      window.clearTimeout(timer);
      const delay = nextThemeBoundary(new Date()).getTime() - Date.now() + 20;
      timer = window.setTimeout(refresh, Math.max(1000, delay));
    };
    refresh();
    const interval = window.setInterval(refresh, 60_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", refresh);
    };
  }, []);
}

export function SiteHeader(props: {
  active: keyof typeof PAGE_NAME;
  onLogout?: () => void;
  backHref?: string;
}): JSX.Element {
  const [toolsOpen, setToolsOpen] = useState(false);
  const [toolsBox, setToolsBox] = useState({ top: 60, left: 12 });
  const [themeMode, setThemeMode] = useState<ThemeMode>("auto");
  const [themeOpen, setThemeOpen] = useState(false);
  const [themeBox, setThemeBox] = useState({ top: 60, left: 12 });
  const headerRef = useRef<HTMLElement>(null);
  const stackHref = stackEntryHref(window.location.hostname);
  useEffect(() => {
    const sync = () => setThemeMode(readThemeMode());
    sync();
    window.addEventListener("fp-theme", sync);
    return () => window.removeEventListener("fp-theme", sync);
  }, []);
  useEffect(() => {
    if (!toolsOpen && !themeOpen) return;
    const close = () => {
      setToolsOpen(false);
      setThemeOpen(false);
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && headerRef.current?.contains(event.target)) return;
      close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("hashchange", close);
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("hashchange", close);
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [toolsOpen, themeOpen]);
  function chooseTheme(mode: ThemeMode) {
    writeThemeMode(mode);
    setThemeMode(mode);
    applyTheme(mode);
    setThemeOpen(false);
  }
  function toggleTheme(event: MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    setThemeBox({
      top: rect.bottom + 4,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - 120)),
    });
    setThemeOpen((open) => !open);
    setToolsOpen(false);
  }
  function toggleTools(event: MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const width = 180;
    setToolsBox({
      top: rect.bottom + 4,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
    });
    setToolsOpen((open) => !open);
    setThemeOpen(false);
  }
  return (
    <header ref={headerRef} className="site-header">
      <a className="site-brand" href={props.active === "catalog" ? "#/" : "/"}>
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path fill="currentColor" d="M12 2.5a9.5 9.5 0 1 0 0 19 9.5 9.5 0 0 0 0-19zm0 2.2c1.6 2.4 2.5 5 2.6 7.3H9.4c.1-2.3 1-4.9 2.6-7.3zM7.2 12h3.1c-.1 2.4-1 5.1-2.6 7.4A7.3 7.3 0 0 1 7.2 12zm6.5 0h3.1a7.3 7.3 0 0 1-.5 7.4c-1.6-2.3-2.5-5-2.6-7.4zM9.4 10h5.2c-.1-2.3-1-5-2.6-7.3C10.4 5 9.5 7.7 9.4 10z" />
        </svg>
        <span className="site-brand-home">耗材选色站</span>
        <span className="site-brand-page">{PAGE_NAME[props.active]}</span>
      </a>
      <nav className="site-nav" aria-label="全站">
        <a href="/" className={props.active === "catalog" ? "site-link is-active" : "site-link"} aria-current={props.active === "catalog" ? "page" : undefined}>耗材选色</a>
        {props.active === "detail" ? null : (
          <a href="/models" className={props.active === "gallery" ? "site-link is-active" : "site-link"} aria-current={props.active === "gallery" ? "page" : undefined}>模型画廊</a>
        )}
        <button type="button" className="site-tools-desktop" aria-expanded={toolsOpen} onClick={toggleTools}>工具</button>
        <button
          type="button"
          className="site-theme site-theme-desktop"
          aria-label={`主题 ${THEME_LABEL[themeMode]}`}
          title={`主题：${THEME_LABEL[themeMode]}`}
          aria-expanded={themeOpen}
          aria-haspopup="menu"
          onClick={toggleTheme}
        >
          <ThemeIcon mode={themeMode} size={18} />
        </button>
      </nav>
      <div className="site-actions">
        {props.active === "catalog" ? <a className="site-link site-mobile" href="/models">画廊</a> : null}
        {props.active === "gallery" || props.active === "login" ? <a className="site-link site-mobile" href="/">耗材选色</a> : null}
        {props.backHref ? <a className="site-link model-back" href={props.backHref}>返回画廊</a> : null}
        {props.active === "catalog" ? <a className="site-link" href="/models/login">登录</a> : null}
        {props.onLogout ? <button type="button" onClick={props.onLogout}>退出登录</button> : null}
        <button
          type="button"
          className="site-theme"
          aria-label={`主题 ${THEME_LABEL[themeMode]}`}
          title={`主题：${THEME_LABEL[themeMode]}`}
          aria-expanded={themeOpen}
          aria-haspopup="menu"
          onClick={toggleTheme}
        >
          <ThemeIcon mode={themeMode} size={18} />
        </button>
        <button type="button" className="site-tools" aria-expanded={toolsOpen} onClick={toggleTools}>工具</button>
      </div>
      <div
        className={toolsOpen ? "fp-tools is-open" : "fp-tools"}
        style={{ ["--tools-top" as string]: `${toolsBox.top}px`, ["--tools-left" as string]: `${toolsBox.left}px` }}
        onClick={(event) => {
          if (event.target instanceof Element && event.target.closest("a")) setToolsOpen(false);
        }}
      >
        <a className="nav-link" href="#/photo" tabIndex={toolsOpen ? 0 : -1}>拍照找耗材</a>
        <a className="nav-link" href="#/photo" tabIndex={toolsOpen ? 0 : -1}>开始找色</a>
        <a className="nav-link" href="#/plan" tabIndex={toolsOpen ? 0 : -1}>图片配色</a>
        <a className="nav-link" href="#/cost" tabIndex={toolsOpen ? 0 : -1}>打印成本</a>
        <a className="nav-link" href={stackHref} tabIndex={toolsOpen ? 0 : -1}>叠色</a>
        <a className="nav-link" href={stackHref} tabIndex={toolsOpen ? 0 : -1}>打开叠色</a>
        <a className="nav-link" href="#/specs" tabIndex={toolsOpen ? 0 : -1}>规格索引</a>
      </div>
      <div
        className={themeOpen ? "fp-theme is-open" : "fp-theme"}
        style={{ ["--tools-top" as string]: `${themeBox.top}px`, ["--tools-left" as string]: `${themeBox.left}px` }}
        role="menu"
      >
        {(["auto", "light", "dark"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            role="menuitemradio"
            aria-checked={themeMode === mode}
            aria-label={THEME_LABEL[mode]}
            title={THEME_LABEL[mode]}
            onClick={() => chooseTheme(mode)}
          >
            <ThemeIcon mode={mode} size={16} />
            <span>{THEME_LABEL[mode]}</span>
          </button>
        ))}
      </div>
    </header>
  );
}
