import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows 库存有 when stock says this color id is in stock", async () => {
    const entry = catalog.entries[0];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          hints: { [entry.id]: { in_stock: true, nearby_in_stock: false } },
        }),
      }),
    );
    render(<ColorDetail entry={entry} catalog={catalog} onClose={vi.fn()} onCompare={vi.fn()} />);
    expect(await screen.findByText("库存有")).toBeTruthy();
    expect(screen.getByRole("link", { name: "购买链接" }).getAttribute("href")).toBe(entry.url);
  });

  it("does not badge a nearby color as in stock", async () => {
    const entry = catalog.entries[0];
    const fetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        hints: { [entry.id]: { in_stock: false, nearby_in_stock: true } },
      }),
    });
    vi.stubGlobal("fetch", fetcher);
    render(<ColorDetail entry={entry} catalog={catalog} onClose={vi.fn()} onCompare={vi.fn()} />);
    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(screen.queryByText("库存有")).toBeNull();
    expect(screen.getByRole("link", { name: "购买链接" })).toBeTruthy();
  });

  it("shows print settings only when the entry has them", () => {
    const { unmount } = render(
      <ColorDetail
        entry={{
          ...catalog.entries[0],
          print: {
            nozzle_c: [190, 230],
            bed_c: [35, 35],
            density_g_cm3: 1.24,
            diameter_mm: 1.75,
            orca_url: "https://api.openfilamentdatabase.org/orcaslicer/example.json",
          },
        }}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "颜色详情" });
    expect(dialog.textContent).toContain("打印参数");
    expect(dialog.textContent).toContain("190–230 °C");
    expect(dialog.textContent).toContain("35 °C");
    expect(dialog.textContent).toContain("1.24 g/cm³");
    expect(dialog.textContent).toContain("1.75 mm");
    expect(screen.getByRole("link", { name: "下载耗材预设" }).getAttribute("href")).toContain(
      "orcaslicer/example.json",
    );
    unmount();

    render(
      <ColorDetail
        entry={catalog.entries[0]}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    expect(screen.getByRole("dialog", { name: "颜色详情" }).textContent).not.toContain("打印参数");
  });

  it("shows the cost calculator with the default total", () => {
    render(
      <ColorDetail
        entry={catalog.entries[0]}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={vi.fn()}
      />,
    );
    expect(screen.getByRole("region", { name: "打印成本" }).textContent).toContain("3.86 元");
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
    fireEvent.click(screen.getByRole("dialog", { name: "颜色详情" }).querySelector(".btn-primary")!);
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(screen.getByRole("button", { name: /eSUN PETG-Basic/ }));
    fireEvent.click(screen.getByRole("dialog", { name: "颜色详情" }).querySelector(".btn-primary")!);
    expect(screen.getByRole("complementary", { name: "对比栏" }).textContent).toContain("9.8");
  });

  it("calls onSelect for similar item and onCompare for its compare button", () => {
    const onSelect = vi.fn();
    const onCompare = vi.fn();
    render(
      <ColorDetail
        entry={catalog.entries[0]}
        catalog={catalog}
        onClose={vi.fn()}
        onCompare={onCompare}
        onSelect={onSelect}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "颜色详情" });
    const similarButton = dialog.querySelector(".similar-item");
    expect(similarButton).not.toBeNull();
    fireEvent.click(similarButton!);
    expect(onSelect).toHaveBeenCalledWith("esun/petg-basic/black");
    expect(onCompare).not.toHaveBeenCalled();

    const compareButtons = screen.getAllByRole("button", { name: "加入对比" });
    // First is the detail primary action; the rest are per similar row.
    expect(compareButtons.length).toBeGreaterThan(1);
    fireEvent.click(compareButtons[1]!);
    expect(onCompare).toHaveBeenCalledWith("esun/petg-basic/black");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("switches detail to a similar color that is not on the current page", async () => {
    const pageSize = 48;
    const base = catalog.entries[0];
    const esun = catalog.entries[1];
    const padded = Array.from({ length: pageSize + 5 }, (_, index) => ({
      ...base,
      id: `pad/${index}`,
      en: `Pad ${index}`,
      zh: `填充${index}`,
      hex: ["#ABCDEF"],
      b: "cailab",
    }));
    // Put the similar target after the first page so it is not among visible swatches.
    const farSimilar = {
      ...esun,
      id: "esun/petg-basic/far-black",
      en: "Far Black",
      zh: "远端黑",
    };
    const bigCatalog = {
      ...catalog,
      entries: [base, ...padded, farSimilar],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => bigCatalog }));
    render(<App />);
    await screen.findByText(`共 ${bigCatalog.entries.length} 个颜色 · 已显示 ${pageSize}`);
    expect(screen.queryByRole("button", { name: /远端黑/ })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Bambu Lab PETG Basic黑色/ }));
    const dialog = await screen.findByRole("dialog", { name: "颜色详情" });
    expect(dialog.textContent).toContain("Black");
    const similarFar = Array.from(dialog.querySelectorAll(".similar-item")).find((node) =>
      (node.textContent ?? "").includes("远端黑"),
    );
    expect(similarFar).toBeTruthy();
    fireEvent.click(similarFar!);
    const updated = await screen.findByRole("dialog", { name: "颜色详情" });
    expect(updated.textContent).toContain("Far Black");
    expect(updated.textContent).toContain("远端黑");
    // Pagination must stay on the first page after the detail switch.
    expect(screen.getByText(`共 ${bigCatalog.entries.length} 个颜色 · 已显示 ${pageSize}`)).toBeTruthy();
  });

  it("keeps loaded swatches when opening and closing a detail drawer", async () => {
    const pageSize = 48;
    const bigCatalog = {
      ...catalog,
      entries: Array.from({ length: 60 }, (_, index) => ({
        ...catalog.entries[0],
        id: `item/${index}`,
        en: `Color ${index}`,
        zh: `颜色${index}`,
      })),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => bigCatalog }));
    const { container } = render(<App />);
    await screen.findByText(`共 60 个颜色 · 已显示 ${pageSize}`);
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    expect(screen.getByText("共 60 个颜色 · 已显示 60")).toBeTruthy();
    expect(container.querySelectorAll(".swatch-card")).toHaveLength(60);

    fireEvent.click(screen.getByRole("button", { name: /颜色0/ }));
    expect(await screen.findByRole("dialog", { name: "颜色详情" })).toBeTruthy();
    expect(screen.getByText("共 60 个颜色 · 已显示 60")).toBeTruthy();
    expect(container.querySelectorAll(".swatch-card")).toHaveLength(60);

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(screen.queryByRole("dialog", { name: "颜色详情" })).toBeNull();
    expect(screen.getByText("共 60 个颜色 · 已显示 60")).toBeTruthy();
    expect(container.querySelectorAll(".swatch-card")).toHaveLength(60);
  });

});
