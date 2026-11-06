import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import result from "./fixtures/result.example.json";
import errorResult from "./fixtures/result.error.example.json";
import { cardSrc } from "../api";
import { PlanPage } from "../components/PlanPage";
import type { PlanResult } from "../types";

const fixture = result as PlanResult;
const errorFixture = errorResult as PlanResult;

describe("PlanPage", () => {
  afterEach(() => cleanup());

  it("submits an image and renders the complete plan", async () => {
    const post = vi.fn().mockResolvedValue(fixture);
    render(<PlanPage post={post} />);
    const file = new File([new Uint8Array([137, 80, 78, 71])], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.change(screen.getByPlaceholderText("例：4 色，AMS 一台，只要拓竹 PLA"), {
      target: { value: "4 色" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(file, "4 色");
    expect(await screen.findByText("配色方案（1 色）")).toBeTruthy();
    expect(screen.getByText("#1B1B1D")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("Bambu Lab PLA Tough · 黑色 Black (12101)")).toBeTruthy();
    expect(screen.getByText("ΔE 4.4")).toBeTruthy();
    expect(screen.getByText("接近")).toBeTruthy();
    expect(screen.getByText("同系列方案：Bambu Lab PLA Tough（最大 ΔE 4.4）")).toBeTruthy();
    expect(screen.getByText("需要 1 个料槽")).toBeTruthy();
    expect(screen.getByRole("img", { name: "配色卡" }).getAttribute("src")).toBe(
      "/api/cards/EXAMPLE_TOKEN.png",
    );
  });

  it("renders the second pick and its purchase link", async () => {
    const post = vi.fn().mockResolvedValue(fixture);
    render(<PlanPage post={post} />);
    const file = new File(["image"], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));

    expect(await screen.findByText("ΔE 6.1")).toBeTruthy();
    expect(screen.getByText("勉强")).toBeTruthy();
    expect(
      screen
        .getAllByRole("link", { name: "购买" })
        .find((link) => link.getAttribute("href")?.endsWith("/pla-aero"))
        ?.getAttribute("href"),
    ).toBe("https://jp.store.bambulab.com/products/pla-aero");
  });

  it("marks the GitHub color table pick unavailable and hides prices", async () => {
    render(<PlanPage post={vi.fn().mockResolvedValue(fixture)} />);
    const file = new File(["image"], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));

    const firstPick = await screen.findByText("Bambu Lab PLA Tough · 黑色 Black (12101)");
    const row = firstPick.closest("li")!;
    expect(within(row).getByText("暂未上架").className).toBe("purchase-unavailable");
    expect(within(row).queryByRole("link", { name: "购买" })).toBeNull();
    const hrefs = screen.queryAllByRole("link", { name: "购买" })
      .map((link) => link.getAttribute("href"));
    expect(hrefs.some((href) => href?.toLowerCase().includes("filaments_color_codes"))).toBe(false);
    expect(document.body.textContent).not.toContain("¥");
    expect(document.body.textContent).not.toContain("JPY");
    expect(document.body.textContent).not.toContain("8,080");
  });

  it("shows the pinduoduo link first and the original store as 原链接", async () => {
    const withAlt: PlanResult = {
      ...fixture,
      matches: fixture.matches.map((match) => ({
        ...match,
        picks: match.picks.map((pick) => ({ ...pick })),
      })),
    };
    const search = "https://mobile.pinduoduo.com/search_result.html?search_key=%E6%8B%93%E7%AB%B9";
    withAlt.matches[0].picks[1].url = search;
    withAlt.matches[0].picks[1].alt_url = "https://jp.store.bambulab.com/products/pla-aero";
    render(<PlanPage post={vi.fn().mockResolvedValue(withAlt)} />);
    const file = new File(["image"], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));

    expect(await screen.findByRole("link", { name: "原链接" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "原链接" }).getAttribute("href")).toBe(
      "https://jp.store.bambulab.com/products/pla-aero",
    );
    expect(
      screen
        .getAllByRole("link", { name: "购买" })
        .some((link) => link.getAttribute("href") === search),
    ).toBe(true);
  });

  it("requires an image before submitting", () => {
    const post = vi.fn();
    render(<PlanPage post={post} />);
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByText("请先选择图片")).toBeTruthy();
  });

  it("renders API result errors and rejected errors", async () => {
    const postResult = vi.fn().mockResolvedValue(errorFixture);
    const { unmount } = render(<PlanPage post={postResult} />);
    const file = new File(["image"], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));
    expect(await screen.findByText(errorFixture.error?.message_zh ?? "")).toBeTruthy();
    unmount();

    const postRejected = vi.fn().mockRejectedValue(new Error("图片超过 10MB"));
    render(<PlanPage post={postRejected} />);
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));
    expect(await screen.findByText("图片超过 10MB")).toBeTruthy();
  });

  it("omits the card image when card_path is null", async () => {
    const noCard = { ...fixture, card_path: null };
    const { queryByRole } = render(<PlanPage post={vi.fn().mockResolvedValue(noCard)} />);
    expect(cardSrc(noCard)).toBeNull();
    const file = new File(["image"], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("图片"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始配色" }));
    await screen.findByText("配色方案（1 色）");
    expect(queryByRole("img", { name: "配色卡" })).toBeNull();
  });
});
