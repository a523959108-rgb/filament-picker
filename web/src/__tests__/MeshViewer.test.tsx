import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MeshViewer } from "../components/MeshViewer";

const harness = vi.hoisted(() => ({
  failWebgl: false,
  failLoad: false,
  loads: [] as string[],
  credentials: false,
  controls: [] as {
    enableDamping: boolean;
    zoomToCursor: boolean;
    touches: { ONE: number; TWO: number };
  }[],
  keyTarget: null as HTMLElement | null,
  disposed: 0,
}));

vi.mock("three", () => {
  class Vector3 {
    x = 0;
    y = 0;
    z = 0;
    set(x: number, y: number, z: number) {
      this.x = x;
      this.y = y;
      this.z = z;
      return this;
    }
    copy(other: Vector3) {
      this.x = other.x;
      this.y = other.y;
      this.z = other.z;
      return this;
    }
    add(other: Vector3) {
      this.x += other.x;
      this.y += other.y;
      this.z += other.z;
      return this;
    }
    normalize() {
      const length = Math.hypot(this.x, this.y, this.z) || 1;
      this.x /= length;
      this.y /= length;
      this.z /= length;
      return this;
    }
    multiplyScalar(scale: number) {
      this.x *= scale;
      this.y *= scale;
      this.z *= scale;
      return this;
    }
  }
  class Box3 {
    setFromObject() {
      return this;
    }
    getCenter(target: Vector3) {
      return target.set(0, 0, 0);
    }
    getSize(target: Vector3) {
      return target.set(1, 1, 1);
    }
  }
  class Object3D {
    children: { traverse?: (fn: (object: Object3D) => void) => void }[] = [];
    add(child: { traverse?: (fn: (object: Object3D) => void) => void }) {
      this.children.push(child);
      return this;
    }
    traverse(fn: (object: Object3D) => void) {
      fn(this);
      for (const child of this.children) child.traverse?.(fn);
    }
  }
  class WebGLRenderer {
    domElement = document.createElement("canvas");
    toneMapping = 0;
    outputColorSpace = "";
    constructor() {
      if (harness.failWebgl) throw new Error("no webgl");
    }
    setPixelRatio() {}
    setSize() {}
    setClearColor() {}
    render() {}
    dispose() {
      harness.disposed += 1;
    }
  }
  class Light extends Object3D {
    position = new Vector3();
  }
  return {
    ACESFilmicToneMapping: 4,
    SRGBColorSpace: "srgb",
    TOUCH: { ROTATE: 0, PAN: 1, DOLLY_PAN: 2, DOLLY_ROTATE: 3 },
    Vector3,
    Box3,
    Object3D,
    Scene: class extends Object3D {},
    PerspectiveCamera: class extends Object3D {
      fov = 40;
      aspect = 1;
      near = 0.1;
      far = 100;
      position = new Vector3();
      updateProjectionMatrix() {}
      lookAt() {}
    },
    AmbientLight: class extends Light {
      constructor(_color?: number, _intensity?: number) {
        super();
      }
    },
    HemisphereLight: class extends Light {
      constructor(_sky?: number, _ground?: number, _intensity?: number) {
        super();
      }
    },
    DirectionalLight: class extends Light {
      constructor(_color?: number, _intensity?: number) {
        super();
      }
    },
    WebGLRenderer,
  };
});

vi.mock("three/addons/controls/OrbitControls.js", () => ({
  OrbitControls: class {
    enableDamping = false;
    dampingFactor = 0;
    screenSpacePanning = false;
    zoomToCursor = false;
    minDistance = 0;
    maxDistance = 0;
    target = { copy() { return this; } };
    touches = { ONE: -1, TWO: -1 };
    constructor(_camera: unknown, _element: HTMLElement) {
      harness.controls.push(this);
    }
    update() {}
    dispose() {}
    listenToKeyEvents(element: HTMLElement) {
      harness.keyTarget = element;
    }
  },
}));

vi.mock("three/addons/loaders/GLTFLoader.js", () => ({
  GLTFLoader: class {
    setWithCredentials(value: boolean) {
      harness.credentials = value;
      return this;
    }
    load(url: string, onLoad: (gltf: { scene: { traverse: (fn: (object: object) => void) => void } }) => void, _progress: unknown, onError: (error: unknown) => void) {
      harness.loads.push(url);
      queueMicrotask(() => {
        if (harness.failLoad) {
          onError(new Error("load failed"));
          return;
        }
        onLoad({
          scene: {
            traverse(fn) {
              fn({ geometry: { dispose() {} }, material: { dispose() {} } });
            },
          },
        });
      });
    }
  },
}));

afterEach(() => {
  cleanup();
  harness.failWebgl = false;
  harness.failLoad = false;
  harness.loads = [];
  harness.credentials = false;
  harness.controls = [];
  harness.keyTarget = null;
  harness.disposed = 0;
});

describe("mesh viewer", () => {
  it("mounts a credentialed orbit viewer for a private glb url", async () => {
    const url = "/api/models/sample-01/glb";
    const { getByRole, getByText } = render(<MeshViewer url={url} label="示例方块 01" />);
    expect(getByRole("figure", { name: "示例方块 01 三维预览" })).toBeTruthy();
    await waitFor(() => expect(harness.loads).toEqual([url]));
    expect(harness.credentials).toBe(true);
    expect(harness.controls).toHaveLength(1);
    expect(harness.controls[0].enableDamping).toBe(true);
    expect(harness.controls[0].zoomToCursor).toBe(true);
    expect(harness.controls[0].touches).toEqual({ ONE: 0, TWO: 2 });
    expect(harness.keyTarget?.className).toBe("model-mesh-stage");
    expect(document.querySelector("canvas")).toBeTruthy();
    await waitFor(() => expect(getByText("拖动旋转，滚轮缩放，双指可缩放或平移")).toBeTruthy());
  });

  it("falls back when the mesh cannot be loaded", async () => {
    harness.failLoad = true;
    const { findByText, queryByText } = render(
      <MeshViewer url="/api/models/sample-01/glb" label="示例方块 01" />,
    );
    expect(await findByText("三维预览不可用，以下为图片")).toBeTruthy();
    expect(queryByText("拖动旋转，滚轮缩放，双指可缩放或平移")).toBeNull();
    expect(harness.disposed).toBeGreaterThan(0);
  });

  it("falls back when WebGL is unavailable", async () => {
    harness.failWebgl = true;
    const { findByText } = render(<MeshViewer url="/api/models/sample-01/glb" label="示例方块 01" />);
    expect(await findByText("三维预览不可用，以下为图片")).toBeTruthy();
    expect(document.querySelector("canvas")).toBeNull();
    expect(harness.loads).toEqual([]);
  });
});
