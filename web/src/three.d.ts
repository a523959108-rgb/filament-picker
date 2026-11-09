// three@0.187 publishes JavaScript without bundled declarations.
// These ambient types cover only the viewer. @types/three pulls extra packages
// this app does not use.

declare module "three" {
  export const ACESFilmicToneMapping: number;
  export const SRGBColorSpace: string;
  export const TOUCH: {
    ROTATE: number;
    PAN: number;
    DOLLY_PAN: number;
    DOLLY_ROTATE: number;
  };

  export class Vector3 {
    x: number;
    y: number;
    z: number;
    set(x: number, y: number, z: number): this;
    copy(v: Vector3): this;
    add(v: Vector3): this;
    normalize(): this;
    multiplyScalar(s: number): this;
  }

  export class Box3 {
    setFromObject(object: Object3D): this;
    getCenter(target: Vector3): Vector3;
    getSize(target: Vector3): Vector3;
  }

  export class BufferGeometry {
    dispose(): void;
  }

  export class Material {
    dispose(): void;
  }

  export class Object3D {
    add(object: Object3D): this;
    traverse(callback: (object: Object3D) => void): void;
  }

  export class Scene extends Object3D {}

  export class PerspectiveCamera extends Object3D {
    fov: number;
    aspect: number;
    near: number;
    far: number;
    position: Vector3;
    constructor(fov?: number, aspect?: number, near?: number, far?: number);
    updateProjectionMatrix(): void;
    lookAt(target: Vector3): void;
  }

  export class Light extends Object3D {
    position: Vector3;
  }

  export class AmbientLight extends Light {
    constructor(color?: number, intensity?: number);
  }

  export class HemisphereLight extends Light {
    constructor(skyColor?: number, groundColor?: number, intensity?: number);
  }

  export class DirectionalLight extends Light {
    constructor(color?: number, intensity?: number);
  }

  export class WebGLRenderer {
    domElement: HTMLCanvasElement;
    toneMapping: number;
    outputColorSpace: string;
    constructor(parameters?: { antialias?: boolean; alpha?: boolean });
    setPixelRatio(value: number): void;
    setSize(width: number, height: number, updateStyle?: boolean): void;
    setClearColor(color: number, alpha?: number): void;
    render(scene: Object3D, camera: PerspectiveCamera): void;
    dispose(): void;
  }
}

declare module "three/addons/controls/OrbitControls.js" {
  import type { PerspectiveCamera, Vector3 } from "three";

  export class OrbitControls {
    enableDamping: boolean;
    dampingFactor: number;
    screenSpacePanning: boolean;
    zoomToCursor: boolean;
    minDistance: number;
    maxDistance: number;
    target: Vector3;
    touches: { ONE: number; TWO: number };
    constructor(camera: PerspectiveCamera, domElement?: HTMLElement);
    update(): void;
    dispose(): void;
    listenToKeyEvents(domElement: HTMLElement): void;
  }
}

declare module "three/addons/loaders/GLTFLoader.js" {
  import type { Object3D } from "three";

  export interface GLTF {
    scene: Object3D;
  }

  export class GLTFLoader {
    setWithCredentials(value: boolean): this;
    load(
      url: string,
      onLoad: (gltf: GLTF) => void,
      onProgress?: (event: ProgressEvent) => void,
      onError?: (error: unknown) => void,
    ): void;
  }
}
