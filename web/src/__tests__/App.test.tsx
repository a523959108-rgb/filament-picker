import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import App from "../App";

describe("App", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.location.hash = "";
  });

  it("renders the catalog count and empty swatches", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { container, findByText } = render(<App />);
    expect(await findByText("共 4 个颜色")).toBeTruthy();
    expect(container.querySelectorAll(".swatch-empty")).toHaveLength(2);
  });

  it("links the catalog page to image planning", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { findByRole } = render(<App />);
    const link = await findByRole("link", { name: "图片配色" });
    expect(link.getAttribute("href")).toBe("#/plan");
    expect(link.className).toBe("nav-link");
  });

  it("shows a homepage stack CTA that stays on in-app hash locally", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { findByRole } = render(<App />);
    const cta = await findByRole("link", { name: "打开叠色" });
    expect(cta.getAttribute("href")).toBe("#/stack");
    const nav = await findByRole("link", { name: "叠色" });
    expect(nav.getAttribute("href")).toBe("#/stack");
  });

  it("opens the stack page from the hash", async () => {
    const tray = {
      schema_version: 1,
      updated_at: "2026-11-09T16:56:46+09:00",
      brand_preference: "bambu-lab",
      series_preference: "PLA Basic",
      disclaimer: "test",
      palettes: {
        CMYW: { label: "cmyw", lut_hints: [], slots: [] },
        RYBW: { label: "rybw", lut_hints: [], slots: [] },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("four-color-tray-map")) {
          return { ok: true, json: async () => tray };
        }
        if (url.includes("web-catalog")) {
          return { ok: true, json: async () => sample };
        }
        return { ok: true, json: async () => tray };
      }),
    );
    window.location.hash = "#/stack";
    const { findByRole } = render(<App />);
    expect(await findByRole("heading", { level: 1, name: "叠色（本机引擎）" })).toBeTruthy();
    expect(await findByRole("button", { name: "下载本机任务包" })).toBeTruthy();
  });

  it("opens the cost page from the hash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    window.location.hash = "#/cost";
    const { findByRole, findByLabelText } = render(<App />);
    expect(await findByRole("heading", { level: 1, name: "打印成本" })).toBeTruthy();
    const grams = await findByRole("spinbutton", { name: "用料（克）" });
    fireEvent.change(grams, { target: { value: "1000" } });
    expect((await findByRole("region", { name: "打印成本" })).textContent).toContain("70.36 元");
    expect(await findByLabelText("真链单价")).toBeTruthy();
    expect(await findByRole("button", { name: "复制购买链接" })).toBeTruthy();
  });

  it("shows the plan and a catalog link after a hash change", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { findByText, findByRole } = render(<App />);
    window.location.hash = "#/plan";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await findByText("图片配色（T24）")).toBeTruthy();
    const link = await findByRole("link", { name: "色卡浏览" });
    expect(link.getAttribute("href")).toBe("#/");
    expect(link.className).toBe("nav-link");
    window.location.hash = "#/";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect((await findByRole("link", { name: "图片配色" })).getAttribute("href")).toBe("#/plan");
  });

  it("shows a catalog load error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    const { findByText } = render(<App />);
    expect(await findByText("目录加载失败")).toBeTruthy();
  });
});
