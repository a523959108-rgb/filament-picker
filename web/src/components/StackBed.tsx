import { useEffect, useRef } from "react";
import type { JSX } from "react";
import * as THREE from "three";
import {
  computeBedPreviewCameraPose,
  createBedPlatformMesh,
  createFallbackBedGeometry,
} from "../vendor/lumina/components/bedPlatformGeometry";
import { buildBedTextureSvg } from "../vendor/lumina/components/bedPlatformTexture";
import { resolveBedPlatformColors } from "../vendor/lumina/components/themeConfig";

export type StackBedProps = {
  bedWidthMm: number;
  bedHeightMm: number;
  artworkUrl: string | null;
  artworkWidthMm: number;
  artworkHeightMm: number;
};

function bedSvg(widthMm: number, heightMm: number): string {
  const colors = resolveBedPlatformColors("light");
  return buildBedTextureSvg({
    widthMm,
    heightMm,
    colors,
    gridVisible: true,
    luminaMarkDataUrl: null,
    slicerLogoDataUrl: null,
    slicerLogoAspectRatio: 1,
  });
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null || canvas.getContext("webgl") !== null;
  } catch {
    return false;
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`image failed: ${url}`));
    image.src = url;
  });
}

/** Empty (or artwork-topped) printer bed using Lumina's plate geometry and texture. */
export function StackBed({
  bedWidthMm,
  bedHeightMm,
  artworkUrl,
  artworkWidthMm,
  artworkHeightMm,
}: StackBedProps): JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null);
  const flatRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) return;
    let svgUrl = "";
    try {
      svgUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(bedSvg(bedWidthMm, bedHeightMm))}`;
    } catch {
      return;
    }
    let renderer: THREE.WebGLRenderer | null = null;
    let disposed = false;
    const geometries: THREE.BufferGeometry[] = [];
    const materials: THREE.Material[] = [];
    const textures: THREE.Texture[] = [];

    const showFlat = () => {
      const flat = flatRef.current;
      if (flat === null) return;
      flat.src = svgUrl;
      flat.hidden = false;
    };

    if (!hasWebGL()) {
      showFlat();
      return;
    }
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    } catch {
      showFlat();
      return;
    }

    host.querySelectorAll("canvas").forEach((node) => node.remove());
    const canvas = renderer.domElement;
    canvas.className = "stack-bed-gl";
    const display = document.createElement("canvas");
    display.className = "stack-bed-display";
    const displayContext = display.getContext("2d");
    host.appendChild(display);
    host.appendChild(canvas);
    if (flatRef.current !== null) flatRef.current.hidden = true;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0xe8e8ec);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe8e8ec);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 8000);
    const pose = computeBedPreviewCameraPose(bedWidthMm, bedHeightMm, camera.fov);
    camera.position.set(pose.position[0], pose.position[1], pose.position[2]);
    camera.lookAt(pose.target[0], pose.target[1], pose.target[2]);
    scene.add(new THREE.AmbientLight(0xffffff, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 0.85);
    key.position.set(80, -120, 220);
    scene.add(key);

    const geometry = createFallbackBedGeometry(bedWidthMm, bedHeightMm);
    geometries.push(geometry);
    const mesh = createBedPlatformMesh(geometry);
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    materials.push(...mats);
    scene.add(mesh);

    const paint = () => {
      if (disposed || renderer === null || displayContext === null) return;
      renderer.render(scene, camera);
      if (display.width !== canvas.width || display.height !== canvas.height) {
        display.width = canvas.width;
        display.height = canvas.height;
      }
      displayContext.drawImage(canvas, 0, 0);
    };
    const resize = () => {
      if (renderer === null) return;
      const width = Math.max(1, host.clientWidth);
      const height = Math.max(1, host.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      paint();
    };

    void loadImage(svgUrl)
      .then((image) => {
        if (disposed) return;
        const texture = new THREE.Texture(image);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.needsUpdate = true;
        textures.push(texture);
        const surface = mats[0];
        if (surface instanceof THREE.MeshStandardMaterial) {
          surface.map = texture;
          surface.needsUpdate = true;
        }
        paint();
      })
      .catch(() => {
        if (!disposed) showFlat();
      });

    if (artworkUrl !== null) {
      void loadImage(artworkUrl)
        .then((image) => {
          if (disposed) return;
          const texture = new THREE.Texture(image);
          texture.colorSpace = THREE.SRGBColorSpace;
          texture.needsUpdate = true;
          textures.push(texture);
          const planeGeo = new THREE.PlaneGeometry(
            Math.min(artworkWidthMm, bedWidthMm * 0.8),
            Math.min(artworkHeightMm, bedHeightMm * 0.8),
          );
          geometries.push(planeGeo);
          const planeMat = new THREE.MeshBasicMaterial({ map: texture, transparent: true });
          materials.push(planeMat);
          const artwork = new THREE.Mesh(planeGeo, planeMat);
          artwork.position.z = 0.6;
          scene.add(artwork);
          paint();
        })
        .catch(() => undefined);
    }

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => resize());
      observer.observe(host);
    }
    resize();

    return () => {
      disposed = true;
      observer?.disconnect();
      canvas.remove();
      display.remove();
      renderer?.dispose();
      for (const item of geometries) item.dispose();
      for (const item of materials) item.dispose();
      for (const item of textures) item.dispose();
    };
  }, [artworkHeightMm, artworkUrl, artworkWidthMm, bedHeightMm, bedWidthMm]);

  return (
    <div ref={hostRef} className="stack-bed-host" aria-label="打印热床">
      <img ref={flatRef} alt="" hidden className="stack-bed-flat" />
    </div>
  );
}
