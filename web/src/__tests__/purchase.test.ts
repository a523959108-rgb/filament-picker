import { describe, expect, it } from "vitest";
import { isGithubColorTableUrl, purchaseHref } from "../purchase";

describe("purchase URLs", () => {
  it.each([
    [
      "https://github.com/bambulab/BambuStudio/blob/master/resources/profiles/BBL/filament/filaments_color_codes.json",
      true,
      null,
    ],
    [
      "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json",
      true,
      null,
    ],
    [
      "https://jp.store.bambulab.com/products/petg-basic",
      false,
      "https://jp.store.bambulab.com/products/petg-basic",
    ],
    [
      "https://github.com/bambulab/BambuStudio",
      false,
      "https://github.com/bambulab/BambuStudio",
    ],
    ["not a url", false, null],
    ["https://GITHUB.COM/example/FILAMENTS_COLOR_CODES.json", true, null],
    ["https://RAW.GITHUBUSERCONTENT.COM/example/FILAMENTS_COLOR_CODES.json", true, null],
    [
      "https://example.com/filaments_color_codes.json",
      false,
      "https://example.com/filaments_color_codes.json",
    ],
    [
      "https://github.com/example?file=filaments_color_codes",
      false,
      "https://github.com/example?file=filaments_color_codes",
    ],
  ])("classifies %s", (url, isColorTable, href) => {
    expect(isGithubColorTableUrl(url)).toBe(isColorTable);
    expect(purchaseHref(url)).toBe(href);
  });

  it.each(["", "   "])("omits empty purchase URL %j", (url) => {
    expect(purchaseHref(url)).toBeNull();
  });
});
