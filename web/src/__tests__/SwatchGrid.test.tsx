import { describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import { SwatchGrid } from "../components/SwatchGrid";
import type { WebEntry } from "../types";

describe("SwatchGrid pagination", () => {
  it("renders only the first page and loads more on demand", () => {
    const entries = Array.from({ length: 60 }, (_, index) => ({
      ...(sample.entries[0] as WebEntry),
      id: `item/${index}`,
      en: `Color ${index}`,
    }));
    const { container, unmount } = render(
      <SwatchGrid entries={entries} brands={sample.brands} pageSize={12} />,
    );
    expect(screen.getByText("共 60 个颜色 · 已显示 12")).toBeTruthy();
    expect(container.querySelectorAll(".swatch-card")).toHaveLength(12);
    fireEvent.click(screen.getByRole("button", { name: /加载更多/ }));
    expect(container.querySelectorAll(".swatch-card")).toHaveLength(24);
    expect(screen.getByText("共 60 个颜色 · 已显示 24")).toBeTruthy();
    unmount();
    cleanup();
  });

  it("hides the load-more control when everything fits", () => {
    const { queryByRole, unmount } = render(
      <SwatchGrid
        entries={sample.entries as WebEntry[]}
        brands={sample.brands}
        pageSize={48}
      />,
    );
    expect(queryByRole("button", { name: /加载更多/ })).toBeNull();
    unmount();
    cleanup();
  });
});
