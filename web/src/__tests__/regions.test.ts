import { describe, expect, it } from "vitest";
import { regionFromDrag } from "../regions";

describe("regionFromDrag", () => {
  it("turns a drag into a normalized rectangle", () => {
    expect(regionFromDrag({ x: 0.5, y: 0.7 }, { x: 0.1, y: 0.2 }, 300, 200)).toEqual({
      space: "norm",
      x: 0.1,
      y: 0.2,
      w: 0.4,
      h: 0.5,
    });
  });

  it("turns a click into a point with the default radius", () => {
    expect(regionFromDrag({ x: 0.25, y: 0.5 }, { x: 0.25, y: 0.5 }, 300, 200)).toEqual({
      space: "norm",
      x: 0.25,
      y: 0.5,
      r: 0.04,
    });
  });

  it("rejects a hairline drag as a point", () => {
    expect(regionFromDrag({ x: 0.2, y: 0.2 }, { x: 0.201, y: 0.5 }, 300, 200)).toEqual({
      space: "norm",
      x: 0.201,
      y: 0.5,
      r: 0.04,
    });
  });
});
