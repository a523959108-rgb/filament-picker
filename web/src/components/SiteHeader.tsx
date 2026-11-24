import { useState } from "react";
import type { JSX } from "react";
import { stackEntryHref } from "../config";

const PAGE_NAME = {
  catalog: "耗材选色",
  gallery: "模型画廊",
  detail: "模型详情",
  login: "登录",
} as const;

export function SiteHeader(props: {
  active: keyof typeof PAGE_NAME;
  onLogout?: () => void;
  backHref?: string;
}): JSX.Element {
  const [toolsOpen, setToolsOpen] = useState(false);
  const stackHref = stackEntryHref(window.location.hostname);
  return (
    <header className="site-header">
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
        <button type="button" className="site-tools-desktop" aria-expanded={toolsOpen} onClick={() => setToolsOpen((open) => !open)}>工具</button>
      </nav>
      <div className="site-actions">
        {props.active === "catalog" ? <a className="site-link site-mobile" href="/models">画廊</a> : null}
        {props.active === "gallery" || props.active === "login" ? <a className="site-link site-mobile" href="/">耗材选色</a> : null}
        {props.backHref ? <a className="site-link model-back" href={props.backHref}>返回画廊</a> : null}
        {props.active === "catalog" ? <a className="site-link" href="/models/login">登录</a> : null}
        {props.onLogout ? <button type="button" onClick={props.onLogout}>退出登录</button> : null}
        <button type="button" className="site-tools" aria-expanded={toolsOpen} onClick={() => setToolsOpen((open) => !open)}>工具</button>
      </div>
      <div className={toolsOpen ? "fp-tools is-open" : "fp-tools"}>
        <a className="nav-link" href="#/photo" tabIndex={toolsOpen ? 0 : -1}>拍照找耗材</a>
        <a className="nav-link" href="#/photo" tabIndex={toolsOpen ? 0 : -1}>开始找色</a>
        <a className="nav-link" href="#/plan" tabIndex={toolsOpen ? 0 : -1}>图片配色</a>
        <a className="nav-link" href="#/cost" tabIndex={toolsOpen ? 0 : -1}>打印成本</a>
        <a className="nav-link" href={stackHref} tabIndex={toolsOpen ? 0 : -1}>叠色</a>
        <a className="nav-link" href={stackHref} tabIndex={toolsOpen ? 0 : -1}>打开叠色</a>
        <a className="nav-link" href="#/specs" tabIndex={toolsOpen ? 0 : -1}>规格索引</a>
      </div>
    </header>
  );
}
