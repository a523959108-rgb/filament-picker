/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { BoxGeometry, Mesh, MeshBasicMaterial, PerspectiveCamera, Group } from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { frame } from "../components/MeshViewer";

describe("derived mesh framing", () => {
  it("fills a wide canvas with a flat z-up pair instead of a few pixels", () => {
    const group = new Group();
    for (const x of [125, 148]) {
      const bead = new Mesh(new BoxGeometry(3.7, 3.7, 2.2), new MeshBasicMaterial());
      bead.position.set(x, 163, 1);
      group.add(bead);
    }
    group.updateMatrixWorld(true);
    const camera = new PerspectiveCamera(40, 700 / 480, 0.1, 1000);
    const controls = new OrbitControls(camera, document.createElement("canvas"));
    frame(camera, controls, group);
    const projected = group.children.map((child) => {
      const point = child.position.clone().project(camera);
      return { x: point.x, y: point.y };
    });
    const spanX = Math.abs(projected[0].x - projected[1].x);
    const midY = (projected[0].y + projected[1].y) / 2;
    expect(spanX).toBeGreaterThan(0.35);
    expect(Math.abs(midY)).toBeLessThan(0.45);
    expect(projected.every((point) => Math.abs(point.x) < 1 && Math.abs(point.y) < 1)).toBe(true);
    controls.dispose();
  });
});
