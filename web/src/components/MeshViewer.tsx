import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  ACESFilmicToneMapping,
  AmbientLight,
  Box3,
  DirectionalLight,
  HemisphereLight,
  PerspectiveCamera,
  Plane,
  Scene,
  SRGBColorSpace,
  TOUCH,
  Vector3,
  WebGLRenderer,
} from "three";
import type { BufferGeometry, Material, MeshStandardMaterial, Object3D } from "three";

type MeshState = "loading" | "ready" | "error";

interface DisposableObject extends Object3D {
  geometry?: BufferGeometry;
  material?: Material | Material[];
}

function disposeHierarchy(root: Object3D): void {
  root.traverse((object) => {
    const candidate = object as DisposableObject;
    candidate.geometry?.dispose();
    const material = candidate.material;
    if (Array.isArray(material)) {
      for (const item of material) item.dispose();
    } else {
      material?.dispose();
    }
  });
}

const FRAME_LIMIT = 0.84;

function boxCorners(box: Box3): Vector3[] {
  const points: Vector3[] = [];
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) points.push(new Vector3(x, y, z));
    }
  }
  return points;
}

function projectedExtent(camera: PerspectiveCamera, points: Vector3[]): number {
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  let extent = 0;
  for (const point of points) {
    const projected = point.clone().project(camera);
    if (!Number.isFinite(projected.x) || !Number.isFinite(projected.y) || projected.z < -1 || projected.z > 1) {
      return Number.POSITIVE_INFINITY;
    }
    extent = Math.max(extent, Math.abs(projected.x), Math.abs(projected.y));
  }
  return extent;
}

export function frame(camera: PerspectiveCamera, controls: OrbitControls, object: Object3D): void {
  const box = new Box3().setFromObject(object);
  if (!box.min || !box.max || !Number.isFinite(box.min.x) || !Number.isFinite(box.max.x)) return;
  const center = box.getCenter(new Vector3());
  const points = boxCorners(box);
  camera.up.set(0, 0, 1);
  const direction = new Vector3(0.65, -1, 0.45).normalize();
  const radius = Math.max(box.getSize(new Vector3()).length() * 0.5, 1);
  const place = (distance: number) => {
    camera.position.copy(center).add(direction.clone().multiplyScalar(distance));
    camera.near = Math.max(distance / 500, 0.01);
    camera.far = Math.max(distance * 80, radius * 20);
    camera.lookAt(center);
  };
  let low = radius * 0.2;
  let high = radius * 40;
  place(high);
  if (projectedExtent(camera, points) > FRAME_LIMIT) return;
  for (let step = 0; step < 24; step += 1) {
    const mid = (low + high) / 2;
    place(mid);
    if (projectedExtent(camera, points) <= FRAME_LIMIT) high = mid;
    else low = mid;
  }
  place(high);
  controls.target.copy(center);
  controls.minDistance = high * 0.25;
  controls.maxDistance = high * 8;
  controls.update();
  camera.updateMatrixWorld(true);
  const after = projectedExtent(camera, points);
  if (after > FRAME_LIMIT && Number.isFinite(after)) {
    place(high * (after / FRAME_LIMIT) * 1.05);
    controls.update();
  }
}

export function MeshViewer({ url, label, controls = false }: {
  url: string; label: string; controls?: boolean;
}): JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef<PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const rootRef = useRef<Object3D | null>(null);
  const homeRef = useRef<{ x: number; y: number; z: number; tx: number; ty: number; tz: number } | null>(null);
  const [state, setState] = useState<MeshState>("loading");
  const [wire, setWire] = useState(false);
  const [clip, setClip] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch {
      setState("error");
      return;
    }
    let frameId = 0;
    let stopped = false;
    const scene = new Scene();
    const camera = new PerspectiveCamera(40, 1, 0.01, 100);
    camera.up.set(0, 0, 1);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.className = "model-mesh-canvas";
    host.append(renderer.domElement);

    scene.add(new AmbientLight(0xffffff, 0.45));
    scene.add(new HemisphereLight(0xffffff, 0x8d97a6, 0.85));
    const key = new DirectionalLight(0xffffff, 1.35);
    key.position.set(3, 5, 4);
    scene.add(key);

    const controls = new OrbitControls(camera, renderer.domElement);
    cameraRef.current = camera;
    controlsRef.current = controls;
    renderer.localClippingEnabled = true;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.zoomToCursor = true;
    controls.touches = { ONE: TOUCH.ROTATE, TWO: TOUCH.DOLLY_PAN };
    controls.listenToKeyEvents(host);

    const resize = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width < 2 || height < 2) return;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      if (rootRef.current) {
        frame(camera, controls, rootRef.current);
        homeRef.current = {
          x: camera.position.x, y: camera.position.y, z: camera.position.z,
          tx: controls.target.x, ty: controls.target.y, tz: controls.target.z,
        };
      }
    };
    resize();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    observer?.observe(host);

    const render = () => {
      frameId = window.requestAnimationFrame(render);
      controls.update();
      renderer.render(scene, camera);
    };
    render();

    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      window.cancelAnimationFrame(frameId);
      observer?.disconnect();
      controls.dispose();
      disposeHierarchy(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
    const fail = () => {
      if (stopped) return;
      stopped = true;
      release();
      setState("error");
    };

    const loader = new GLTFLoader();
    loader.setWithCredentials(true);
    loader.load(
      url,
      (gltf) => {
        if (stopped) {
          disposeHierarchy(gltf.scene);
          return;
        }
        scene.add(gltf.scene);
        rootRef.current = gltf.scene;
        resize();
        frame(camera, controls, gltf.scene);
        homeRef.current = {
          x: camera.position.x, y: camera.position.y, z: camera.position.z,
          tx: controls.target.x, ty: controls.target.y, tz: controls.target.z,
        };
        setState("ready");
      },
      undefined,
      fail,
    );

    return () => {
      stopped = true;
      release();
    };
  }, [url]);

  const caption =
    state === "error"
      ? "三维预览不可用，以下为图片"
      : state === "ready"
        ? "拖动旋转，滚轮缩放，双指可缩放或平移"
        : "三维预览加载中…";

  function restyle(nextWire: boolean, nextClip: boolean) {
    const root = rootRef.current;
    if (root === null) return;
    const plane = new Plane(new Vector3(0, 1, 0), 0);
    root.traverse((object) => {
      const material = (object as DisposableObject).material;
      const list = Array.isArray(material) ? material : material ? [material] : [];
      for (const item of list) {
        const surface = item as MeshStandardMaterial;
        surface.wireframe = nextWire;
        surface.clippingPlanes = nextClip ? [plane] : [];
        surface.needsUpdate = true;
      }
    });
  }

  return (
    <figure className="model-mesh" aria-busy={state === "loading"} aria-label={`${label} 三维预览`}>
      {state === "ready" && controls && (
        <div className="model-mesh-tools" role="group" aria-label="网格">
          <button type="button" onClick={() => {
            const camera = cameraRef.current;
            const orbit = controlsRef.current;
            const root = rootRef.current;
            if (!camera || !orbit || !root) return;
            frame(camera, orbit, root);
            homeRef.current = {
              x: camera.position.x, y: camera.position.y, z: camera.position.z,
              tx: orbit.target.x, ty: orbit.target.y, tz: orbit.target.z,
            };
          }}>归位</button>
          <button type="button" aria-pressed={wire} onClick={() => {
            const next = !wire;
            setWire(next);
            restyle(next, clip);
          }}>线框</button>
          <button type="button" aria-pressed={clip} onClick={() => {
            const next = !clip;
            setClip(next);
            restyle(wire, next);
          }}>剖切</button>
        </div>
      )}
      <div
        ref={hostRef}
        className="model-mesh-stage"
        hidden={state === "error"}
        tabIndex={state === "error" ? -1 : 0}
      />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
