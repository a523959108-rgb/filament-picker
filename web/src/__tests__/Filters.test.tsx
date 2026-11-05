import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import sample from "../../../docs/fixtures/web-catalog.sample.json";
import App from "../App";

describe("catalog filters", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    window.location.hash = "";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => sample }));
  });

  it("filters official colors and combines the filter with search", async () => {
    render(<App />);
    expect(await screen.findByText("共 4 个颜色")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("只看官方色"));
    expect(await screen.findByText("共 1 个颜色")).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "樱花" } });
    expect(await screen.findByText("共 0 个颜色")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("只看官方色"));
    await waitFor(() => expect(screen.getByText("共 1 个颜色")).toBeTruthy());
    expect(screen.getByText("樱花粉")).toBeTruthy();
  });
});
