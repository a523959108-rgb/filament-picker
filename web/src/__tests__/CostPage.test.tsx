import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { CostPage } from "../components/CostPage";

describe("CostPage market offers", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.location.hash = "#/cost";
  });

  it("shows goods price text and can apply CNY card price to the calculator", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });

    const { findByText, findByRole, findAllByRole } = render(<CostPage />);
    expect(await findByText("¥34.5 CNY（商品卡价，非单色价）")).toBeTruthy();
    expect(await findByText(/共 1 条 PDD 商品真链/)).toBeTruthy();

    fireEvent.click(await findByRole("button", { name: "用到计算器" }));
    const price = await findByRole("spinbutton", { name: "耗材单价（元/千克）" });
    expect((price as HTMLInputElement).value).toBe("34.5");

    fireEvent.click((await findAllByRole("button", { name: "复制购买链接" }))[0]);
    expect(writeText).toHaveBeenCalledWith(
      "https://mobile.pinduoduo.com/goods.html?goods_id=931315367733",
    );
  });

  it("shows placeholder when a goods link has no price_text", async () => {
    const catalog = {
      ...sample,
      entries: [
        {
          ...sample.entries[0],
          id: "bambu-lab/pla-basic/black-10101",
          b: "bambu-lab",
          s: "PLA Basic",
          zh: "黑色",
          en: "Black",
          url: "https://mobile.pinduoduo.com/goods.html?goods_id=646322960873",
          price: null,
        },
      ],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => catalog }));
    const { findByText } = render(<CostPage />);
    expect(await findByText("暂无报价")).toBeTruthy();
    expect(await findByText(/尚无 price_text/)).toBeTruthy();
  });
});
