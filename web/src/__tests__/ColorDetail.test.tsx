import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import App from "../App";

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
    expect(screen.getByRole("link", { name: "购买链接" }).getAttribute("href")).toBe(
      "https://jp.store.bambulab.com/products/petg-basic",
    );
    expect(screen.getByRole("dialog", { name: "颜色详情" }).textContent).toContain("eSUN");
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
