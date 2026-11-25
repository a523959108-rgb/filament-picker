import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { PhotoPage, PhotoResults, type PhotoColor } from "../components/PhotoPage";
import type { WebCatalog } from "../types";

const catalog = sample as WebCatalog;

describe("PhotoPage", () => {
  afterEach(() => cleanup());

  it("shows extracted matches and a stack link when the color is far", () => {
    const colors: PhotoColor[] = [
      { hex: "#00FF00", share: 0.62, source: "auto" },
      { hex: "#2244AA", share: 0.3, source: "auto" },
    ];
    const { getByRole, getByText, getAllByText } = render(
      <PhotoResults colors={colors} entries={catalog.entries} brands={catalog.brands} hostname="localhost" />,
    );
    expect(getByText(/Bambu Lab/)).toBeTruthy();
    expect(getAllByText(/ΔE /).length).toBeGreaterThan(0);
    expect(getByRole("heading", { name: "叠色建议" })).toBeTruthy();
    const link = getByRole("link", { name: "用这个颜色打开叠色" });
    expect(link.getAttribute("href")).toBe("#/stack?colors=00FF00&mode=RYBW");
    const all = getByRole("link", { name: "带入全部主色" });
    expect(all.getAttribute("href")).toBe("#/stack?colors=00FF00,2244AA&mode=RYBW");
  });

  it("hides the stack offer when a catalog color is exact", () => {
    const { queryByRole, getByText } = render(
      <PhotoResults
        colors={[{ hex: "#000000", share: 1, source: "auto" }]}
        entries={catalog.entries}
        brands={catalog.brands}
        hostname="filament.ibaozi.com"
      />,
    );
    expect(getByText("几乎一样")).toBeTruthy();
    expect(getByText(/¥2,800 JPY/)).toBeTruthy();
    expect(queryByRole("heading", { name: "叠色建议" })).toBeNull();
  });

  it("rejects a non-image file before decoding", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const { findByLabelText, findByRole } = render(<PhotoPage />);
    await findByRole("heading", { level: 1, name: "拍照找耗材" });
    const input = await findByLabelText("选择照片");
    const file = new File([new Uint8Array([1, 2, 3])], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });
    expect((await findByRole("alert")).textContent).toMatch(/JPG/);
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("allows removing a manual picked color chip", () => {
    const onRemove = vi.fn();
    const { getByRole } = render(
      <PhotoResults
        colors={[
          { hex: "#123456", share: null, source: "manual" },
          { hex: "#000000", share: 1, source: "auto" },
        ]}
        entries={catalog.entries}
        brands={catalog.brands}
        hostname="localhost"
        onRemoveColor={onRemove}
      />,
    );
    fireEvent.click(getByRole("button", { name: "移除 #123456" }));
    expect(onRemove).toHaveBeenCalledWith("#123456");
  });
});
