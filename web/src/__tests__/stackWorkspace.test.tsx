import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import trayMap from "../../../data/four-color-tray-map.json";
import catalog from "../../public/web-catalog.json";
import { StackPage } from "../components/StackPage";
import { moveSlot } from "../stackSlots";

describe("moveSlot", () => {
  it("moves an item to the drop index", () => {
    expect(moveSlot(["R", "Y", "B", "W"], 0, 2)).toEqual(["Y", "B", "R", "W"]);
    expect(moveSlot(["R", "Y", "B", "W"], 3, 1)).toEqual(["R", "W", "Y", "B"]);
    expect(moveSlot(["R", "Y", "B", "W"], 1, 1)).toEqual(["R", "Y", "B", "W"]);
    expect(moveSlot(["R", "Y"], -1, 0)).toEqual(["R", "Y"]);
  });
});

describe("StackPage workspace", () => {
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

  it("reorders color slots by drag and drop", async () => {
    const { findByRole } = render(<StackPage />);
    const list = await findByRole("list", { name: "四色槽" });
    const slotItems = () =>
      within(list).getAllByRole("listitem").filter((item) => item.hasAttribute("data-slot"));
    await waitFor(() => expect(slotItems().map((item) => item.getAttribute("data-slot"))).toEqual(["R", "Y", "B", "W"]));
    const items = slotItems();
    const source = items[0];
    const target = items[2];
    if (source === undefined || target === undefined) throw new Error("slots missing");
    fireEvent.dragStart(source);
    fireEvent.dragOver(target);
    fireEvent.drop(target);
    expect(slotItems().map((item) => item.getAttribute("data-slot"))).toEqual(["Y", "B", "R", "W"]);
  });

  it("keeps the advanced panel collapsed until opened", async () => {
    const { findByRole, queryByLabelText, findByLabelText } = render(<StackPage />);
    const toggle = await findByRole("button", { name: "高级" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(queryByLabelText("回传导入")).toBeNull();
    expect(queryByLabelText("粘贴回传 JSON")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(await findByLabelText("回传导入")).toBeTruthy();
    expect(document.getElementById("stack-advanced")?.textContent).toContain("scripts/run_lumina_stack_job.py");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(queryByLabelText("粘贴回传 JSON")).toBeNull();
  });
});
