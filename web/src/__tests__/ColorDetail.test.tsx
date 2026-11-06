import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import App from "../App";
import { ColorDetail } from "../components/ColorDetail";
import type { WebCatalog } from "../types";

const catalog = sample as WebCatalog;

describe("color detail and compare", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.location.hash = "";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
  });

  it("opens bambu detail with its source, link, and similar color", async () => {
    render(<App />);
    await screen.findByText("共 4 个颜色");
    fireEvent.click(screen.getByRole("button", { name: /Bambu Lab PETG Basic/ }));

    expect(screen.getByText("#000000")).toBeTruthy();
    expect(screen.getByText("官方色值")).toBeTruthy();
    const bambu = catalog.entries[0];
    expect(bambu.url.startsWith("https://mobile.pinduoduo.com/search_result.html?search_key=")).toBe(
      true,
    );
    expect(bambu.url.includes("goods_id")).toBe(false);
    expect(screen.getByRole("link", { name: "购买链接" }).getAttribute("href")).toBe(bambu.url);
    expect(screen.getByRole("link", { name: "原链接" }).getAttribute("href")).toBe(
      "https://jp.store.bambulab.com/products/petg-basic",
    );
    expect(screen.getByRole("dialog", { name: "颜色详情" }).textContent).toContain("eSUN");
    const detailText = screen.getByRole("dialog", { name: "颜色详情" }).textContent;
    expect(detailText).not.toContain("¥");
    expect(detailText).not.toContain("JPY");
    expect(detailText).not.toContain("2,800");
  });

  it.each([
    "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json",
    "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json",
    "not a url",
    "   ",
  ])("shows unavailable purchase text for %s", (url) => {
    render(
      <ColorDetail
        entry={{ ...catalog.entries[0], url }}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    expect(screen.getByText("暂未上架").className).toBe("purchase-unavailable");
    expect(screen.queryByRole("link", { name: "购买链接" })).toBeNull();
  });

  it("keeps a real pinduoduo goods link and omits the alternate", () => {
    const entry = catalog.entries.find((item) => item.id === "byehassle/pla-ya-guang/sakura-bloom");
    if (entry === undefined) throw new Error("missing byehassle sample");
    render(
      <ColorDetail entry={entry} catalog={catalog} onClose={vi.fn()} onCompare={vi.fn()} />,
    );
    expect(screen.getByRole("link", { name: "购买链接" }).getAttribute("href")).toBe(
      "https://mobile.pinduoduo.com/goods.html?goods_id=931315367733",
    );
    expect(screen.queryByRole("link", { name: "原链接" })).toBeNull();
  });

  it("omits the purchase entry when its URL is empty", () => {
    render(
      <ColorDetail
        entry={{ ...catalog.entries[0], url: "" }}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    expect(screen.queryByText("暂未上架")).toBeNull();
    expect(screen.queryByRole("link", { name: "购买链接" })).toBeNull();
  });

  it("shows the store swatch badge for esun", async () => {
    render(<App />);
    await screen.findByText("共 4 个颜色");
    fireEvent.click(screen.getByRole("button", { name: /eSUN PETG-Basic/ }));
    expect(screen.getByText("店铺示意色（近似）")).toBeTruthy();
  });

  it("adds two entries to the compare bar", async () => {
    render(<App />);
    await screen.findByText("共 4 个颜色");
    fireEvent.click(screen.getByRole("button", { name: /Bambu Lab PETG Basic/ }));
    fireEvent.click(screen.getByRole("button", { name: "加入对比" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(screen.getByRole("button", { name: /eSUN PETG-Basic/ }));
    fireEvent.click(screen.getByRole("button", { name: "加入对比" }));
    expect(screen.getByRole("complementary", { name: "对比栏" }).textContent).toContain("9.8");
  });
});
