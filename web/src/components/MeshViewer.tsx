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

export function frame(camera: PerspectiveCamera, controls: OrbitControls, object: Object3D): void {
  const box = new Box3().setFromObject(object);
  const center = box.getCenter(new Vector3());
  const size = box.getSize(new Vector3());
  camera.up.set(0, 0, 1);
  const aspect = Number.isFinite(camera.aspect) && camera.aspect > 0.2 ? camera.aspect : 1;
  const vFov = (camera.fov * Math.PI) / 180;
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
  const direction = new Vector3(0.65, -1, 0.45).normalize();
  const right = new Vector3().crossVectors(direction, new Vector3(0, 0, 1));
  if (right.lengthSq() < 1e-8) right.set(1, 0, 0);
  right.normalize();
  const up = new Vector3().crossVectors(right, direction).normalize();
  const half = new Vector3(Math.max(size.x, 1e-3) / 2, Math.max(size.y, 1e-3) / 2, Math.max(size.z, 1e-3) / 2);
  const projected = (axis: Vector3) =>
    Math.abs(axis.x) * half.x + Math.abs(axis.y) * half.y + Math.abs(axis.z) * half.z;
  const distance = Math.max(
    projected(right) / Math.tan(hFov / 2),
    projected(up) / Math.tan(vFov / 2),
    1,
  ) * 1.12;
  camera.position.copy(center).add(direction.multiplyScalar(distance));
  camera.near = Math.max(distance / 200, 0.01);
  camera.far = Math.max(distance * 40, 100);
  camera.updateProjectionMatrix();
  camera.lookAt(center);
  controls.target.copy(center);
  controls.minDistance = distance * 0.35;
  controls.maxDistance = distance * 6;
  controls.update();
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
      const width = host.clientWidth || 640;
      const height = host.clientHeight || 420;
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      if (rootRef.current) frame(camera, controls, rootRef.current);
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
            const home = homeRef.current;
            const camera = cameraRef.current;
            if (!home || !camera) return;
            camera.position.set(home.x, home.y, home.z);
            controlsRef.current?.target.set(home.tx, home.ty, home.tz);
            controlsRef.current?.update();
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
