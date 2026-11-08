import type { JSX } from "react";
import { CostCalculator } from "./CostCalculator";

export function CostPage(): JSX.Element {
  return (
    <section className="cost-page">
      <header className="topbar">
        <div className="topbar-title">
          <h1>打印成本</h1>
          <p className="topbar-sub">按用料和电费估算一次打印要花多少钱</p>
        </div>
        <nav className="topbar-nav" aria-label="页面导航">
          <a href="#/" className="nav-link">色卡浏览</a>
          <a href="#/plan" className="nav-link">图片配色</a>
        </nav>
      </header>
      <div className="panel cost-panel">
        <CostCalculator />
      </div>
    </section>
  );
}
