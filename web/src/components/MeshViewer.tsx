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
  Scene,
  SRGBColorSpace,
  TOUCH,
  Vector3,
  WebGLRenderer,
} from "three";
import type { BufferGeometry, Material, Object3D } from "three";

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

function frame(camera: PerspectiveCamera, controls: OrbitControls, object: Object3D): void {
  const box = new Box3().setFromObject(object);
  const center = box.getCenter(new Vector3());
  const size = box.getSize(new Vector3());
  const span = Math.max(size.x, size.y, size.z);
  const radius = (Number.isFinite(span) && span > 0 ? span : 1) * 0.5;
  const fov = (camera.fov * Math.PI) / 180;
  const distance = (radius / Math.sin(fov / 2)) * 1.35;
  const offset = new Vector3().set(0.75, 0.55, 1).normalize().multiplyScalar(distance);
  camera.position.copy(center).add(offset);
  camera.near = Math.max(distance / 200, 0.001);
  camera.far = Math.max(distance * 200, 10);
  camera.updateProjectionMatrix();
  camera.lookAt(center);
  controls.target.copy(center);
  controls.minDistance = distance * 0.25;
  controls.maxDistance = distance * 8;
  controls.update();
}

export function MeshViewer({ url, label }: { url: string; label: string }): JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<MeshState>("loading");

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setState("error");
      return;
    }
    let frameId = 0;
    let stopped = false;
    const scene = new Scene();
    const camera = new PerspectiveCamera(40, 1, 0.01, 100);
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
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.zoomToCursor = true;
    controls.touches = { ONE: TOUCH.ROTATE, TWO: TOUCH.DOLLY_PAN };
    controls.listenToKeyEvents(host);

    const resize = () => {
      const width = host.clientWidth || 320;
      const height = host.clientHeight || 240;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
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
        frame(camera, controls, gltf.scene);
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

  return (
    <figure className="model-mesh" aria-busy={state === "loading"} aria-label={`${label} 三维预览`}>
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
