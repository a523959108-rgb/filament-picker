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
    const fetcher = vi.fn().mockResolvedValue(response({ username: "yulanmoxing" }));
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    const { getByLabelText, getByRole } = render(<ModelPreview path="/models/login" navigate={navigate} />);
    fireEvent.change(getByLabelText("用户名"), { target: { value: "yulanmoxing" } });
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
    fireEvent.change(getByLabelText("用户名"), { target: { value: "yulanmoxing" } });
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
