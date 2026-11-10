import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import trayMap from "../../../data/four-color-tray-map.json";
import catalog from "../../public/web-catalog.json";
import { StackPage } from "../components/StackPage";

describe("StackPage", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.location.hash = "#/stack";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("four-color-tray-map")) {
          return { ok: true, json: async () => trayMap };
        }
        if (url.includes("web-catalog")) {
          return { ok: true, json: async () => catalog };
        }
        return { ok: false, status: 404, json: async () => ({}) };
      }),
    );
  });

  it("renders smoke model, cascaded red recommend, and download controls", async () => {
    const { findByRole, findByText, findByLabelText, findAllByText } = render(<StackPage />);

    expect(await findByRole("heading", { level: 1, name: "叠色（本机引擎）" })).toBeTruthy();
    expect(await findByLabelText("烟测模型与推荐色")).toBeTruthy();
    expect(await findByRole("button", { name: "预览" })).toBeTruthy();
    expect(await findByRole("link", { name: "源码" })).toBeTruthy();
    fireEvent.click(await findByRole("button", { name: "预览" }));
    expect(await findByRole("img", { name: "叠色预览图" })).toBeTruthy();
    expect(await findByRole("link", { name: "下载 3MF 模型" })).toBeTruthy();
    expect((await findAllByText(/bambu-lab\/pla-basic\/light-gray-10104/)).length).toBeGreaterThan(0);
    expect((await findAllByText(/bambu-lab\/pla-basic\/cobalt-blue-10604/)).length).toBeGreaterThan(0);
    expect((await findAllByText(/bambu-lab\/pla-matte\/scarlet-red-11200/)).length).toBeGreaterThan(0);
    expect((await findAllByText(/同品牌回退/)).length).toBeGreaterThan(0);
    expect((await findAllByText(/PDD 真链/)).length).toBeGreaterThan(0);
    expect(await findByLabelText("四槽推荐色卡")).toBeTruthy();

    expect(await findByLabelText("任务参数")).toBeTruthy();
    expect((await findAllByText(/bambu-lab\/pla-matte\/scarlet-red-11200/)).length).toBeGreaterThan(0);
    fireEvent.change(await findByLabelText("LUT 色模式"), { target: { value: "CMYW" } });
    expect(await findByText(/bambu-lab\/pla-basic\/cyan-10603/)).toBeTruthy();
    expect(await findByRole("button", { name: "生成 3MF" })).toBeTruthy();
    expect(document.querySelector("#stack-advanced")).toBeNull();
    fireEvent.click(await findByRole("button", { name: "高级" }));
    expect(await findByLabelText("回传导入")).toBeTruthy();
    expect((await findAllByText(/本站不跑 GPL/)).length).toBeGreaterThan(0);
  });

  it("imports pasted result JSON and refreshes recommendations", async () => {
    const { findByLabelText, findByRole, findAllByText, findByText } = render(<StackPage />);
    await findByLabelText("四槽推荐色卡");
    fireEvent.click(await findByRole("button", { name: "高级" }));

    const payload = {
      schema_version: 1,
      kind: "lumina-stack-result",
      created_at: "2026-11-09T18:10:00+09:00",
      lut_mode: "RYBW",
      source_job_kind: "lumina-stack-job",
      preview_relpath: "stack-smoke/preview.png",
      model_3mf_relpath: "stack-smoke/smoke_rybw_sample_logo.3mf",
      slots: [
        { extruder: 1, slot: "W", name_zh: "白", name_en: "White", engine_hex: "#D7D2CF" },
        { extruder: 2, slot: "R", name_zh: "红", name_en: "Red", engine_hex: "#E94A39" },
        { extruder: 3, slot: "Y", name_zh: "黄", name_en: "Yellow", engine_hex: "#ECEF35" },
        { extruder: 4, slot: "B", name_zh: "蓝", name_en: "Blue", engine_hex: "#3451B1" },
      ],
      note: "paste-test",
    };
    fireEvent.change(await findByLabelText("粘贴回传 JSON"), {
      target: { value: JSON.stringify(payload) },
    });
    fireEvent.click(await findByRole("button", { name: "应用粘贴内容" }));
    expect(await findByText(/已导入并刷新/)).toBeTruthy();
    expect((await findAllByText(/bambu-lab\/pla-matte\/scarlet-red-11200/)).length).toBeGreaterThan(0);
  });

  it("downloads a zip job package when clicked", async () => {
    const click = vi.fn();
    const createElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = createElement(tag);
      if (tag === "a") {
        Object.defineProperty(el, "click", { value: click });
      }
      return el;
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:job"),
      revokeObjectURL: vi.fn(),
    });

    const { findByRole, findByText } = render(<StackPage />);
    fireEvent.click(await findByRole("button", { name: "生成 3MF" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(await findByText(/已下载任务包/)).toBeTruthy();
  });
});
