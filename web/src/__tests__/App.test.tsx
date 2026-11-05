import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
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

  it("shows the plan placeholder after a hash change", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { findByText } = render(<App />);
    window.location.hash = "#/plan";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(await findByText("图片配色（T24）")).toBeTruthy();
  });

  it("shows a catalog load error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    const { findByText } = render(<App />);
    expect(await findByText("目录加载失败")).toBeTruthy();
  });
});
