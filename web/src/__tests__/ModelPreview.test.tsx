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
      const url = new URL(fetcher.mock.calls.at(-1)?.[0], "http://localhost");
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
    expect((await findByRole("img", { name: "示例方块 01 盘面 1" })).getAttribute("src"))
      .toBe(detailed.images[0].url);
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
    expect(await findByText("盘面 1")).toBeTruthy();
    expect((await findByRole("img", { name: "示例方块 01 盘面 1" })).getAttribute("src"))
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
    expect(await findByRole("img", { name: "示例方块 01 盘面 1" })).toBeTruthy();
    expect(queryByRole("img", { name: /三维预览/ })).toBeNull();
  });

  it("maps each print plate to its slots, including duplicate and unknown colors", async () => {
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
              settings_id: "PLA Basic", used_g: null,
              picks: [{
                id: "white", name: "白色", brand_name: "Bambu Lab", series_name: "PLA Basic",
                hex: "#FFFFFF", delta_e: 0.2, label: "几乎一样",
              }],
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
    const { findByText, getByText, getByRole, container } = render(
      <ModelPreview path="/models/sample-01" />,
    );
    expect(await findByText("眼白")).toBeTruthy();
    expect(getByText("body.stl")).toBeTruthy();
    expect(getByText("eye.stl")).toBeTruthy();
    expect(getByText("槽位 3")).toBeTruthy();
    expect(getByText("槽位 7")).toBeTruthy();
    expect(getByText("PLA Basic")).toBeTruthy();
    expect(getByText("PETG")).toBeTruthy();
    expect(getByText(/12\.5 g/)).toBeTruthy();
    expect(getByText("未命名")).toBeTruthy();
    expect(getByText("未记录部件")).toBeTruthy();
    expect(getByText("槽位未知")).toBeTruthy();
    expect(getByText("颜色未知")).toBeTruthy();
    expect(getByText(/部件没有单独的槽位记录/)).toBeTruthy();
    expect(container.querySelectorAll(".model-plate")).toHaveLength(2);
    expect(container.querySelector(".model-plate.is-active")?.textContent).toContain("盘 1");
    fireEvent.click(getByRole("button", { name: "对应盘 2" }));
    expect(container.querySelector(".model-plate.is-active")?.textContent).toContain("盘 2");
    expect(container.querySelector(".model-plate.is-active")?.textContent).toContain("当前盘");
  });

  it("says the plate mapping is unknown when it was not stored", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...model, plates: null })));
    const { findByText, getByLabelText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByText(/不能判断哪一盘用什么颜色/)).toBeTruthy();
    expect(getByLabelText("#112233")).toBeTruthy();
  });

  it("shows an empty plate record without inventing colors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...model, colours: [], colour_matches: [], plates: [],
    })));
    const { findByText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByText("没有打印盘记录。")).toBeTruthy();
    expect(await findByText("没有配色数据。")).toBeTruthy();
  });

  it("keeps the original unavailable and does not download the mesh", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...model,
      mesh_url: "/api/models/sample-01/glb",
      original: {
        available: false, reason: "not_stored", filename: "示例.3mf",
        size_bytes: null, sha256: null, media_type: null, url: null,
      },
    })));
    const { findByRole, getByRole, findByText } = render(<ModelPreview path="/models/sample-01" />);
    expect(await findByText(/记录的文件名：示例\.3mf/)).toBeTruthy();
    expect(await findByText(/不能代替原始模型/)).toBeTruthy();
    fireEvent.click(getByRole("button", { name: /原件未入库/ }));
    expect((await findByRole("alert")).textContent).toContain("请先保留本地备份");
  });

  it("downloads the original only after the byte count and checksum match", async () => {
    const bytes = Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8]);
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes.buffer))].map(
      (part) => part.toString(16).padStart(2, "0"),
    ).join("");
    const original = {
      available: true, reason: null, filename: "多盘示例.3mf", size_bytes: bytes.byteLength,
      sha256: sha, media_type: "model/3mf", url: "/api/models/sample-01/original",
    };
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url === original.url) {
        return Promise.resolve({
          ok: true, status: 200,
          headers: new Headers({ "X-Content-SHA256": sha }),
          arrayBuffer: async () => bytes.buffer,
          json: async () => ({}),
        });
      }
      return Promise.resolve(response({ ...model, original }));
    });
    vi.stubGlobal("fetch", fetcher);
    URL.createObjectURL = vi.fn(() => "blob:model");
    URL.revokeObjectURL = vi.fn();
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicks.push(this.download);
    });
    const { findByRole } = render(<ModelPreview path="/models/sample-01" />);
    fireEvent.click(await findByRole("button", { name: /下载 示例方块 01 的原件/ }));
    await waitFor(() => expect(clicks).toEqual(["多盘示例.3mf"]));
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe(original.url);
    expect(fetcher.mock.calls.at(-1)?.[1].credentials).toBe("same-origin");
  });

  it("cancels a download whose size does not match and surfaces server errors", async () => {
    const original = {
      available: true, reason: null, filename: "多盘示例.3mf", size_bytes: 99,
      sha256: "abc", media_type: "model/3mf", url: "/api/models/sample-01/original",
    };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ ...model, original }))
      .mockResolvedValueOnce({
        ok: true, status: 200, headers: new Headers(),
        arrayBuffer: async () => Uint8Array.from([1, 2, 3]).buffer,
        json: async () => ({}),
      });
    vi.stubGlobal("fetch", fetcher);
    const { findByRole, findByText } = render(<ModelPreview path="/models/sample-01" />);
    fireEvent.click(await findByRole("button", { name: /下载 示例方块 01 的原件/ }));
    expect(await findByText(/字节数和记录不一致/)).toBeTruthy();
  });

  it("reports a failed original upload", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(model))
      .mockResolvedValueOnce({
        ok: false, status: 400, headers: new Headers(),
        json: async () => ({ detail: "文件不是可重新打开的 3MF 或 STL" }),
      });
    vi.stubGlobal("fetch", fetcher);
    const { findByLabelText, findByRole } = render(<ModelPreview path="/models/sample-01" />);
    const input = await findByLabelText("补存原件");
    const file = new File([Uint8Array.from([1])], "broken.3mf", { type: "application/octet-stream" });
    fireEvent.change(input, { target: { files: [file] } });
    expect((await findByRole("alert")).textContent).toContain("可重新打开");
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe("/api/models/sample-01/original");
    expect(fetcher.mock.calls.at(-1)?.[1].method).toBe("POST");
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
