import type { JSX, ReactNode } from "react";
import { SOURCE_URL, stackEntryHref } from "../config";

export type SitePage = "catalog" | "photo" | "plan" | "cost" | "stack" | "models";

export interface SiteHeaderProps {
  page: SitePage;
  title: string;
  subtitle?: string;
  headerClassName?: string;
  navClassName?: string;
  showSource?: boolean;
  extraActions?: ReactNode;
}

export function SiteHeader({
  page,
  title,
  subtitle,
  headerClassName = "topbar",
  navClassName = "topbar-nav",
  showSource = false,
  extraActions,
}: SiteHeaderProps): JSX.Element {
  const hostname = window.location.hostname;
  const stackHref = stackEntryHref(hostname);

  const items: { key: SitePage; label: string; href: string }[] = [
    ...(page === "catalog" ? [] : [{ key: "catalog" as const, label: "色卡浏览", href: "#/" }]),
    { key: "photo", label: "拍照找耗材", href: "#/photo" },
    { key: "plan", label: "图片配色", href: "#/plan" },
    { key: "cost", label: "打印成本", href: "#/cost" },
    { key: "stack", label: "叠色", href: stackHref },
  ];

  return (
    <header className={headerClassName}>
      <div className="topbar-title">
        <h1>{title}</h1>
        {subtitle ? <p className="topbar-sub">{subtitle}</p> : null}
      </div>
      <nav className={navClassName} aria-label="页面导航">
        {items
          .filter((item) => item.key !== page)
          .map((item) => (
            <a key={item.key} href={item.href} className="nav-link">
              {item.label}
            </a>
          ))}
        {page !== "models" && (
          <a href="/models/login" className="nav-link">
            模型预览
          </a>
        )}
        {showSource && (
          <a className="nav-link" href={SOURCE_URL} target="_blank" rel="noreferrer">
            源码
          </a>
        )}
        {extraActions}
      </nav>
    </header>
  );
}
