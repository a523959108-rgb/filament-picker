import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import App from "../App";
import type { WebCatalog, WebEntry } from "../types";

const catalog = sample as WebCatalog;

function withFifth(): WebCatalog {
  const fifth: WebEntry = { ...(catalog.entries[0] as WebEntry), id: "extra/fifth", zh: "第五色", en: "Fifth", hex: ["#123456"] };
  return { ...catalog, entries: [...catalog.entries, fifth] };
}

describe("catalog chrome", () => {
  afterEach(() => cleanup());

  it("filters from the brand bar and caps compare at four", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => withFifth() }));
    render(<App />);
    expect(await screen.findByText("共 5 个颜色")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "品牌" }));
    fireEvent.click(screen.getByRole("button", { name: "eSUN" }));
    expect(screen.getByText("品牌：eSUN")).toBeTruthy();
    expect(screen.getByText("共 1 个颜色")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "品牌" }));
    fireEvent.click(screen.getByRole("button", { name: "全部品牌" }));
    for (const button of screen.getAllByRole("button", { name: "对比" })) fireEvent.click(button);
    expect(screen.getByRole("status").textContent).toContain("最多对比 4 个");
    expect(screen.getByRole("complementary", { name: "对比栏" }).textContent).toContain("4/4");
    fireEvent.click(screen.getAllByRole("button", { name: "移除" })[0]!);
    expect(screen.getByRole("complementary", { name: "对比栏" }).textContent).toContain("3/4");
  });
});
