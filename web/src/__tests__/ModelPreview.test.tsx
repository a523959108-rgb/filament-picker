import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import App from "../App";
import { ModelPreview } from "../components/ModelPreview";

vi.mock("../components/MeshViewer", () => ({
  MeshViewer: ({ url, label }: { url: string; label: string }) => (
    <div role="img" aria-label={`${label} 三维预览`} data-url={url} />
  ),
}));

const model = {
  id: "sample-01", title: "示例方块 01", series: "几何", author: "样例作者",
  size_bytes: 2048, plate_count: 2, colours: ["#FFFFFF", "#112233"],
  thumb_url: "/api/models/sample-01/thumb", created_at: "2026-11-06T12:00:00+09:00",
};
const listing = { items: [model], total: 25, page: 1, page_size: 12, series: ["几何"], authors: ["样例作者"] };
function response(data: unknown, status = 200) {
  return { ok: status === 200, status, json: async () => data };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("model preview", () => {
  it("renders login fields through the pathname branch without fetching the color catalog", () => {
    window.history.replaceState({}, "", "/models/login");
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const { getByLabelText } = render(<App />);
    expect(getByLabelText("用户名")).toBeTruthy();
    expect(getByLabelText("密码").getAttribute("type")).toBe("password");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("submits login and navigates to the gallery", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ username: "preview-tester" }));
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    const { getByLabelText, getByRole } = render(<ModelPreview path="/models/login" navigate={navigate} />);
    fireEvent.change(getByLabelText("用户名"), { target: { value: "preview-tester" } });
    // The mocked request tests form behavior without a stored password fixture.
    fireEvent.change(getByLabelText("密码"), { target: { value: crypto.randomUUID() } });
    fireEvent.click(getByRole("button", { name: "登录" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/models"));
    expect(fetcher.mock.calls[0][0]).toBe("/api/models/login");
    expect(fetcher.mock.calls[0][1].credentials).toBe("same-origin");
  });

  it("shows failed login and rate limit messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 429)));
    const { getByLabelText, getByRole, findByRole } = render(<ModelPreview path="/models/login" />);
    fireEvent.change(getByLabelText("用户名"), { target: { value: "preview-tester" } });
    fireEvent.change(getByLabelText("密码"), { target: { value: crypto.randomUUID() } });
    fireEvent.click(getByRole("button", { name: "登录" }));
    expect((await findByRole("alert")).textContent).toContain("稍后重试");
  });

  it("renders gallery cards, banner, filters and pagination", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(listing));
    vi.stubGlobal("fetch", fetcher);
    const { findByText, getByRole, getByLabelText } = render(<ModelPreview path="/models" />);
    expect(await findByText(model.title)).toBeTruthy();
    expect(getByRole("note").textContent).toBe("仅私人收藏预览、禁止外传");
    expect(getByRole("img", { name: model.title }).getAttribute("src")).toBe(model.thumb_url);
    expect(getByRole("link", { name: model.title }).getAttribute("href")).toBe("/models/sample-01");
    fireEvent.click(getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(fetcher.mock.calls.at(-1)?.[0]).toContain("page=2"));
    fireEvent.change(getByLabelText("系列"), { target: { value: "几何" } });
    fireEvent.change(getByLabelText("作者"), { target: { value: "样例作者" } });
    fireEvent.change(getByLabelText("搜索模型"), { target: { value: "方块" } });
    fireEvent.click(getByRole("button", { name: "搜索" }));
    await waitFor(() => {
      const url = new URL(String(fetcher.mock.calls.at(-1)?.[0] ?? ""), "http://localhost");
      expect(url.searchParams.get("q")).toBe("方块");
      expect(url.searchParams.get("series")).toBe("几何");
      expect(url.searchParams.get("author")).toBe("样例作者");
      expect(url.searchParams.get("page")).toBe("1");
    });
  });

  it("renders plate and top shots, plain description, and filament matches", async () => {
    const detailed = {
      ...model,
      description: "说明 <img src=x onerror=alert(1)>",
      images: [
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
        { kind: "top" as const, plate: 1, url: "/api/models/sample-01/media/top_1.png" },
      ],
      colour_matches: [{
        hex: "#112233",
        picks: [{
          id: "bambu-lab/petg-basic/black-30105",
          name: "黑色 Black (30105)",
          brand_name: "Bambu Lab",
          series_name: "PETG Basic",
          hex: "#000000",
          delta_e: 1.2,
          label: "几乎一样",
        }],
      }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const { findByRole, getByText, container } = render(<ModelPreview path="/models/sample-01" />);
    expect((await findByRole("img", { name: "示例方块 01 斜视 1" })).getAttribute("src"))
      .toBe(detailed.images[0].url);
    expect(container.querySelectorAll(".model-plate-card")).toHaveLength(1);
    fireEvent.click(getByText("盘 1"));
    fireEvent.click(getByText("俯视"));
    expect(getByText("俯视 1")).toBeTruthy();
    const description = container.querySelector(".model-description");
    expect(description?.textContent).toContain("<img");
    expect(description?.querySelector("img")).toBeNull();
    expect(getByText(/几乎一样/)).toBeTruthy();
    expect(getByText(/Bambu Lab/)).toBeTruthy();
  });

  it("shows 库存有 on a model color that is in stock", async () => {
    const detailed = {
      ...model,
      images: [],
      colour_matches: [{
        hex: "#000000",
        picks: [{
          id: "bambu-lab/petg-basic/black-30105",
          name: "黑色 Black (30105)",
          brand_name: "Bambu Lab",
          series_name: "PETG Basic",
          hex: "#000000",
          delta_e: 0,
          label: "几乎一样",
          stock: { in_stock: true, nearby_in_stock: false },
        }],
      }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const { findByText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByText(/库存有/)).toBeTruthy();
    expect(await findByText(/Bambu Lab/)).toBeTruthy();
  });

  it("uses the cover photo on the card and as the detail hero", async () => {
    const cover = "/api/models/sample-01/media/cover.png";
    const covered = {
      ...model,
      cover_url: cover,
      images: [
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
        { kind: "cover" as const, plate: 0, url: cover },
      ],
    };
    const fetcher = vi.fn().mockResolvedValue(response({ ...listing, items: [covered] }));
    vi.stubGlobal("fetch", fetcher);
    const gallery = render(<ModelPreview path="/models" />);
    expect((await gallery.findByRole("img", { name: model.title })).getAttribute("src")).toBe(cover);
    gallery.unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(covered)));
    const detail = render(<ModelPreview path="/models/sample-01" />);
    expect((await detail.findByRole("img", { name: "示例方块 01 封面" })).getAttribute("src")).toBe(cover);
    expect(detail.getByText("封面")).toBeTruthy();
    expect(detail.getAllByRole("img").map((img) => img.getAttribute("src"))[0]).toBe(cover);
  });

  it("renders detail metadata and original color swatches", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(model)));
    const { findByRole, getByText, getByLabelText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByRole("heading", { name: model.title })).toBeTruthy();
    expect(getByText("2 盘")).toBeTruthy();
    expect(getByText("2.0 KB")).toBeTruthy();
    expect(getByLabelText("#112233")).toBeTruthy();
  });

  it("mounts a private mesh viewer and keeps the image gallery", async () => {
    const detailed = {
      ...model,
      mesh_url: "/api/models/sample-01/glb",
      images: [
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const { findByRole, findByText } = render(<ModelPreview path="/models/sample-01" />);
    const viewer = await findByRole("img", { name: "示例方块 01 三维预览" });
    expect(viewer.getAttribute("data-url")).toBe("/api/models/sample-01/glb");
    expect(await findByText("盘 1")).toBeTruthy();
    expect((await findByRole("img", { name: "示例方块 01 斜视 1" })).getAttribute("src"))
      .toBe(detailed.images[0].url);
  });

  it("keeps today's image gallery when no mesh is published", async () => {
    const detailed = {
      ...model,
      mesh_url: null,
      images: [
        { kind: "cover" as const, plate: 0, url: "/api/models/sample-01/media/cover.png" },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const { findByRole, queryByRole } = render(<ModelPreview path="/models/sample-01" />);
    expect((await findByRole("img", { name: "示例方块 01 封面" })).getAttribute("src"))
      .toBe(detailed.images[0].url);
    expect(queryByRole("img", { name: /三维预览/ })).toBeNull();
  });

  it("ignores an external mesh url and still shows images", async () => {
    const detailed = {
      ...model,
      mesh_url: "https://cdn.example/models/sample-01.glb",
      images: [
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const { findByRole, queryByRole } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByRole("img", { name: "示例方块 01 斜视 1" })).toBeTruthy();
    expect(queryByRole("img", { name: /三维预览/ })).toBeNull();
  });

  it("shows which print plate uses which filament slot", async () => {
    const detailed = {
      ...model,
      plates: [
        {
          index: 1,
          name: "眼白",
          objects: ["body.stl", "eye.stl"],
          filaments: [
            {
              slot: 3, hex: "#FFFFFF", type: "PLA", vendor: "Bambu Lab",
              settings_id: "PLA Basic", used_g: null, picks: [],
            },
            {
              slot: 7, hex: "#FFFFFF", type: "PETG", vendor: "Bambu Lab",
              settings_id: "PETG Basic", used_g: 12.5, picks: [],
            },
          ],
        },
        {
          index: 2,
          name: null,
          objects: [],
          filaments: [{
            slot: null, hex: null, type: "", vendor: "", settings_id: "", used_g: null, picks: [],
          }],
        },
      ],
      images: [
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
        { kind: "plate" as const, plate: 2, url: "/api/models/sample-01/media/plate_2.png" },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const view = render(<ModelPreview path="/models/sample-01" />);
    expect(await view.findByText("点选上面的打印盘，查看盘面、部件和耗材。")).toBeTruthy();
    expect(view.queryByText("槽位 3")).toBeNull();
    expect(view.container.querySelectorAll(".model-plate-card")).toHaveLength(2);
    expect(view.queryByRole("img", { name: /俯视/ })).toBeNull();
    const download = view.getByRole("button", { name: "下载3MF" });
    expect((download as HTMLButtonElement).disabled).toBe(true);
    expect(view.getByText("未接通，暂不能下载")).toBeTruthy();
    fireEvent.click(download);
    expect(vi.mocked(fetch).mock.calls.some((call) => String(call[0]).endsWith("/original"))).toBe(false);
    fireEvent.click(view.getByRole("button", { name: /盘 1 眼白/ }));
    expect(view.getByText("槽位 3")).toBeTruthy();
    expect(view.getByText("槽位 7")).toBeTruthy();
    expect(view.getByText("PETG")).toBeTruthy();
    expect(view.getByLabelText("槽位 3 颜色 #FFFFFF").className).toContain("model-colour");
    expect(view.getByText("body.stl")).toBeTruthy();
    fireEvent.click(view.getByRole("button", { name: /斜视 2/ }));
    expect(view.getByText("未记录部件")).toBeTruthy();
    expect(view.getByText("颜色未知")).toBeTruthy();
    expect(view.queryByText("body.stl")).toBeNull();
    fireEvent.click(view.getByRole("button", { name: /斜视 2/ }));
    expect(view.queryByText("未记录部件")).toBeNull();
    expect(view.getByText("点选上面的打印盘，查看盘面、部件和耗材。")).toBeTruthy();
    fireEvent.click(view.getByRole("button", { name: "收起盘列表" }));
    expect(view.container.querySelector(".model-plate-picker")).toBeNull();
    fireEvent.click(view.getByRole("button", { name: "展开 2 盘" }));
    expect(view.container.querySelectorAll(".model-plate-card")).toHaveLength(2);
  });

  it("keeps a real cover large and leaves other plates collapsed", async () => {
    const cover = "/api/models/sample-01/media/cover.png";
    const detailed = {
      ...model,
      cover_url: cover,
      images: [
        { kind: "cover" as const, plate: 0, url: cover },
        { kind: "plate" as const, plate: 1, url: "/api/models/sample-01/media/plate_1.png" },
        { kind: "plate" as const, plate: 2, url: "/api/models/sample-01/media/plate_2.png" },
      ],
      plates: [
        { index: 1, name: "第一盘", objects: ["a.stl"], filaments: [
          { slot: 1, hex: "#112233", type: "PLA", vendor: "", settings_id: "", used_g: null, picks: [] },
        ] },
        { index: 2, name: null, objects: ["b.stl"], filaments: [
          { slot: 2, hex: "#FFFFFF", type: "PLA", vendor: "", settings_id: "", used_g: null, picks: [] },
        ] },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(detailed)));
    const view = render(<ModelPreview path="/models/sample-01" />);
    const hero = await view.findByRole("img", { name: "示例方块 01 封面" });
    expect(hero.getAttribute("src")).toBe(cover);
    expect(hero.closest(".model-hero")).toBeTruthy();
    expect(view.getByRole("img", { name: "示例方块 01 斜视 1" }).closest(".model-plate-card")).toBeTruthy();
    expect(view.queryByText("a.stl")).toBeNull();
    fireEvent.click(view.getByRole("button", { name: /盘 1 第一盘/ }));
    expect(view.getByText("a.stl")).toBeTruthy();
    expect(view.queryByText("b.stl")).toBeNull();
    expect(view.container.querySelectorAll(".model-plate-card")).toHaveLength(2);
  });

  it("merges repeated part names and keeps one card per plate", async () => {
    const objects = Array.from({ length: 97 }, () => "tooth.stl_3");
    objects.push("eye.stl", "eye.stl");
    for (let index = 0; index < 9; index += 1) objects.push(`extra_${index}.stl`);
    const plates = Array.from({ length: 22 }, (_, index) => ({
      index: index + 1,
      name: index === 10 ? "左眼" : null,
      objects: index === 10 ? objects : ["body.stl"],
      filaments: [{
        slot: index + 1, hex: index === 0 ? "#FFFFFF" : "#112233", type: "PLA", vendor: "Bambu Lab",
        settings_id: "", used_g: null, picks: [],
      }],
    }));
    const images = plates.flatMap((plate) => [
      { kind: "plate" as const, plate: plate.index, url: `/api/models/sample-01/media/plate_${plate.index}.png` },
      { kind: "top" as const, plate: plate.index, url: `/api/models/sample-01/media/top_${plate.index}.png` },
    ]);
    Element.prototype.scrollIntoView = () => undefined;
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...model,
      description: "很长的说明。".repeat(40),
      plate_count: 22,
      plates,
      images,
    })));
    const view = render(<ModelPreview path="/models/sample-01" />);
    expect(await view.findByText("展开说明")).toBeTruthy();
    expect(view.container.querySelectorAll(".model-plate-card")).toHaveLength(22);
    expect(view.container.querySelectorAll(".model-plate-card img")).toHaveLength(22);
    expect(view.queryByText("tooth.stl_3 ×97")).toBeNull();
    fireEvent.click(view.getByRole("button", { name: /盘 11 左眼/ }));
    expect(scroll).not.toHaveBeenCalled();
    const parts = view.container.querySelector(".model-parts");
    expect(parts?.contains(view.getByText("tooth.stl_3 ×97"))).toBe(true);
    expect(view.getByText("eye.stl ×2")).toBeTruthy();
    expect(view.queryAllByText("tooth.stl_3")).toHaveLength(0);
    expect(view.getByRole("button", { name: "俯视" })).toBeTruthy();
    expect(view.queryByRole("button", { name: "正视" })).toBeNull();
    expect(view.container.querySelector(".model-slots")?.contains(view.getByLabelText("槽位 11 颜色 #112233"))).toBe(true);
    expect(view.getByLabelText("槽位 11 颜色 #112233").className).toContain("model-colour");
    const layout = view.container.querySelector(".model-screen");
    expect(layout?.contains(parts ?? null)).toBe(true);
    fireEvent.click(view.getByRole("button", { name: /查看全部/ }));
    const listed = view.container.querySelectorAll(".model-objects li");
    expect(listed.length).toBe(11);
    expect(layout?.contains(view.getByText("extra_8.stl"))).toBe(true);
    const fullText = "很长的说明。".repeat(40);
    fireEvent.click(view.getByRole("button", { name: "展开说明" }));
    const shown = view.container.querySelector(".model-head .model-description");
    expect(shown?.textContent).toBe(fullText);
    expect(shown?.className).not.toContain("is-clamped");
    expect(view.container.querySelector(".model-head")?.contains(shown ?? null)).toBe(true);
    expect(view.queryByRole("dialog")).toBeNull();
    expect(view.container.querySelector("main")?.className).toContain("is-desc-open");
    fireEvent.click(view.getByRole("button", { name: "收起说明" }));
    expect(view.container.querySelector(".model-head .model-description")?.className).toContain("is-clamped");
    expect(view.container.querySelector("main")?.className).not.toContain("is-desc-open");
    expect(view.container.querySelector(".model-plate-picker")).toBeTruthy();
  });

  it("keeps an enabled download beside the long Chinese original name", async () => {
    const filename = "分件版 仙子伊布拉布布labubu （无需AMS）.3mf";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...model,
      original: {
        available: true,
        url: "/api/models/sample-01/original",
        filename,
        size_bytes: null,
        sha256: null,
        media_type: "model/3mf",
      },
    })));
    const view = render(<ModelPreview path="/models/sample-01" />);
    const button = await view.findByRole("button", { name: "下载3MF" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    const status = view.getByText(filename);
    expect(status.id).toBe("model-download-status");
    expect(button.getAttribute("aria-describedby")).toBe("model-download-status");
    expect(status.closest(".model-download-block")?.contains(button)).toBe(true);
    expect(status.closest(".model-download-panel")).toBeTruthy();
    expect(status.closest(".model-head")).toBeNull();
    const head = view.container.querySelector(".model-head");
    const panel = status.closest(".model-download-panel");
    expect(head).toBeTruthy();
    expect(panel).toBeTruthy();
    expect(head && panel ? head.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING : 0).toBeTruthy();
    expect(view.queryByRole("dialog")).toBeNull();
  });

  it("downloads a stored original and leaves the color-only API disabled", async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const fetcher = vi.fn(async (url: string, init?: { credentials?: string }) => {
      if (String(url).endsWith("/original")) {
        return {
          ok: true,
          status: 200,
          headers: { get: () => null },
          arrayBuffer: async () => bytes.buffer,
        };
      }
      if (String(url).endsWith("/scheme")) return response({ slots: [], note: "仅展示色" });
      if (String(url).endsWith("/favorites")) return response({ items: [] });
      return response({
        ...model,
        original: {
          available: true,
          url: "/api/models/sample-01/original",
          filename: "fixture.3mf",
          size_bytes: bytes.byteLength,
          sha256: null,
          media_type: "model/3mf",
        },
      });
    });
    vi.stubGlobal("fetch", fetcher);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const view = render(<ModelPreview path="/models/sample-01" />);
    const button = await view.findByRole("button", { name: "下载3MF" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(view.queryByText(/不能下载/)).toBeNull();
    expect(view.queryByText(/丢失|重新上传|未入库/)).toBeNull();
    fireEvent.click(button);
    await waitFor(() => expect(fetcher.mock.calls.some((call) => call[0] === "/api/models/sample-01/original")).toBe(true));
    const downloadCall = fetcher.mock.calls.find((call) => call[0] === "/api/models/sample-01/original");
    expect(downloadCall?.[1]?.credentials).toBe("same-origin");
  });

  it("says plate mapping is unknown when the record has no layout", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...model, plates: null })));
    const { findByText, getByLabelText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByText(/不能判断哪一盘用什么颜色/)).toBeTruthy();
    expect(getByLabelText("#112233")).toBeTruthy();
  });

  it("restores the gallery page and filters, and falls back when opened directly", async () => {
    window.history.replaceState({}, "", "/models?page=2&q=%E5%B8%83&series=%E5%87%A0%E4%BD%95&author=%E7%8E%8B%E9%93%81%E9%94%A4");
    const fetcher = vi.fn((url: string) => Promise.resolve(
      String(url).startsWith("/api/models?") ? response(listing) : response(model),
    ));
    vi.stubGlobal("fetch", fetcher);
    const gallery = render(<ModelPreview path="/models" />);
    await gallery.findByText(model.title);
    await waitFor(() => {
      const url = new URL(String(fetcher.mock.calls.at(-1)?.[0] ?? ""), "http://localhost");
      expect(url.searchParams.get("page")).toBe("2");
      expect(url.searchParams.get("q")).toBe("布");
      expect(url.searchParams.get("series")).toBe("几何");
      expect(url.searchParams.get("author")).toBe("王铁锤");
    });
    expect(gallery.getByText("2 盘 · 2.0 KB")).toBeTruthy();
    const stored = sessionStorage.getItem("fp.galleryHref");
    gallery.unmount();
    const detail = render(<ModelPreview path="/models/sample-01" />);
    await detail.findByRole("heading", { name: model.title });
    expect(detail.getByRole("link", { name: "返回画廊" }).getAttribute("href")).toBe(stored);
    expect(detail.queryByRole("link", { name: "模型画廊" })).toBeNull();
    expect(stored).toContain("page=2");
    detail.unmount();
    sessionStorage.clear();
    const direct = render(<ModelPreview path="/models/sample-01" />);
    await direct.findByRole("heading", { name: model.title });
    expect(direct.getByRole("link", { name: "返回画廊" }).getAttribute("href")).toBe("/models");
    expect(direct.queryByRole("link", { name: "模型画廊" })).toBeNull();
  });

  it("redirects expired sessions and logs out", async () => {
    const navigate = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 401)));
    const { unmount } = render(<ModelPreview path="/models" navigate={navigate} />);
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/models/login"));
    unmount();
    navigate.mockClear();
    const fetcher = vi.fn().mockResolvedValue(response(listing));
    vi.stubGlobal("fetch", fetcher);
    const { findByText, getByRole } = render(<ModelPreview path="/models" navigate={navigate} />);
    await findByText(model.title);
    fireEvent.click(getByRole("button", { name: "退出登录" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/models/login"));
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe("/api/models/logout");
  });
});
