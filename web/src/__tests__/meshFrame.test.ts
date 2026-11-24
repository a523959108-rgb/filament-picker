/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { Box3, BoxGeometry, Group, Mesh, MeshBasicMaterial, PerspectiveCamera, Vector3 } from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { frame } from "../components/MeshViewer";

const ASPECTS = [745 / 423, 265 / 240, 713 / 420, 335 / 265, 1063 / 423];

function corners(object: Group | Mesh): Vector3[] {
  object.updateMatrixWorld(true);
  const box = new Box3().setFromObject(object);
  const points: Vector3[] = [];
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) points.push(new Vector3(x, y, z));
    }
  }
  return points;
}

function extent(camera: PerspectiveCamera, points: Vector3[]): number {
  camera.updateMatrixWorld(true);
  let max = 0;
  for (const point of points) {
    const projected = point.clone().project(camera);
    max = Math.max(max, Math.abs(projected.x), Math.abs(projected.y));
    expect(projected.z).toBeGreaterThanOrEqual(-1);
    expect(projected.z).toBeLessThanOrEqual(1);
  }
  return max;
}

function view(object: Group | Mesh, aspect: number): number {
  const camera = new PerspectiveCamera(40, aspect, 0.1, 5000);
  camera.up.set(0, 0, 1);
  const controls = new OrbitControls(camera, document.createElement("canvas"));
  frame(camera, controls, object);
  controls.update();
  const max = extent(camera, corners(object));
  controls.dispose();
  return max;
}

describe("derived mesh framing", () => {
  const eye = new Group();
  for (const [x, y] of [[147.6, 162.1], [124.7, 164.6]] as const) {
    const bead = new Mesh(new BoxGeometry(3.7, 3.7, 2.4), new MeshBasicMaterial());
    bead.position.set(x, y, 1);
    eye.add(bead);
  }
  const dryer = new Mesh(new BoxGeometry(210, 220, 51), new MeshBasicMaterial());
  dryer.position.set(131, 140, 25.5);
  const base = new Mesh(new BoxGeometry(150, 150, 18), new MeshBasicMaterial());
  base.position.set(128, 128, 9);

  it.each(ASPECTS)("keeps the eye, base, and dryer corners inside aspect %s", (aspect) => {
    for (const object of [eye, dryer, base]) {
      const max = view(object, aspect);
      expect(max).toBeLessThanOrEqual(0.9);
      expect(max).toBeGreaterThan(0.5);
    }
  });
});
