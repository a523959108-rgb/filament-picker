import type { JSX } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { SiteHeader, useThemeClock } from "../components/SiteHeader";

function ThemeHarness(): JSX.Element {
  useThemeClock();
  return <SiteHeader active="catalog" />;
}
import { applyTheme, nextThemeBoundary, readThemeMode, resolveTheme, writeThemeMode } from "../theme";

function at(hour: number, minute: number): Date {
  return new Date(2026, 10, 25, hour, minute, 0, 0);
}

describe("theme schedule", () => {
  afterEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.themeMode;
  });

  it("uses light from 07:00 inclusive until 19:00 exclusive", () => {
    expect(resolveTheme("auto", at(6, 59))).toBe("dark");
    expect(resolveTheme("auto", at(7, 0))).toBe("light");
    expect(resolveTheme("auto", at(18, 59))).toBe("light");
    expect(resolveTheme("auto", at(19, 0))).toBe("dark");
  });

  it("keeps a manual choice at any time", () => {
    expect(resolveTheme("light", at(3, 0))).toBe("light");
    expect(resolveTheme("dark", at(12, 0))).toBe("dark");
  });

  it("schedules the next local boundary", () => {
    expect(nextThemeBoundary(at(6, 59)).getHours()).toBe(7);
    expect(nextThemeBoundary(at(7, 0)).getHours()).toBe(19);
    expect(nextThemeBoundary(at(18, 59)).getHours()).toBe(19);
    expect(nextThemeBoundary(at(19, 0)).getDate()).toBe(26);
    expect(nextThemeBoundary(at(19, 0)).getHours()).toBe(7);
  });

  it("persists the mode and falls back when storage fails", () => {
    writeThemeMode("dark");
    expect(readThemeMode()).toBe("dark");
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => writeThemeMode("light")).not.toThrow();
    expect(readThemeMode()).toBe("auto");
    setItem.mockRestore();
    getItem.mockRestore();
  });

  it("applies the resolved theme before paint consumers read it", () => {
    expect(applyTheme("auto", at(7, 0))).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.themeMode).toBe("auto");
    applyTheme("dark", at(7, 0));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("switches at the boundary without a reload and clears the timer", () => {
    vi.useFakeTimers();
    vi.setSystemTime(at(18, 59));
    const view = render(<ThemeHarness />);
    expect(document.documentElement.dataset.theme).toBe("light");
    vi.setSystemTime(at(19, 0));
    vi.advanceTimersByTime(70_000);
    expect(document.documentElement.dataset.theme).toBe("dark");
    const clear = vi.spyOn(window, "clearTimeout");
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");
    view.unmount();
    expect(clear).toHaveBeenCalled();
    expect(clearIntervalSpy).toHaveBeenCalled();
    clear.mockRestore();
    clearIntervalSpy.mockRestore();
    cleanup();
    vi.useRealTimers();
  });

  it("re-reads the saved mode when the window regains focus", () => {
    const view = render(<ThemeHarness />);
    writeThemeMode("dark");
    window.dispatchEvent(new Event("focus"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.themeMode).toBe("dark");
    view.unmount();
    cleanup();
  });

  it("closes the tools menu after choosing the spec index", () => {
    const view = render(<SiteHeader active="catalog" />);
    view.getAllByRole("button", { name: "工具" })[0].click();
    const specs = view.getAllByRole("link", { name: "规格索引", hidden: true })[0];
    specs.click();
    expect(view.getAllByRole("button", { name: "工具" })[0].getAttribute("aria-expanded")).toBe("false");
    cleanup();
  });

  it("closes open header menus on hashchange and Escape", () => {
    const view = render(<SiteHeader active="catalog" />);
    const toolsBtn = view.getAllByRole("button", { name: "工具" })[0];
    fireEvent.click(toolsBtn);
    expect(toolsBtn.getAttribute("aria-expanded")).toBe("true");
    fireEvent(window, new Event("hashchange"));
    expect(toolsBtn.getAttribute("aria-expanded")).toBe("false");

    const themeBtn = view.getAllByRole("button", { name: /主题/ })[0];
    fireEvent.click(themeBtn);
    expect(themeBtn.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(themeBtn.getAttribute("aria-expanded")).toBe("false");
    cleanup();
  });
});
