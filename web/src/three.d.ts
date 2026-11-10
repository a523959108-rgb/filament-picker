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
    constructor(x?: number, y?: number, z?: number);
    set(x: number, y: number, z: number): this;
    copy(v: Vector3): this;
    add(v: Vector3): this;
    sub(v: Vector3): this;
    normalize(): this;
    multiplyScalar(s: number): this;
    fromBufferAttribute(attribute: BufferAttribute, index: number): this;
    crossVectors(a: Vector3, b: Vector3): this;
  }

  export class Box3 {
    min: Vector3;
    max: Vector3;
    setFromObject(object: Object3D): this;
    getCenter(target: Vector3): Vector3;
    getSize(target: Vector3): Vector3;
  }

  export class BufferAttribute {
    count: number;
    constructor(array: ArrayLike<number>, itemSize: number);
    getX(index: number): number;
    getY(index: number): number;
  }

  export class BufferGeometry {
    boundingBox: Box3 | null;
    dispose(): void;
    getAttribute(name: string): BufferAttribute;
    getIndex(): BufferAttribute | null;
    setIndex(index: number[]): void;
    clearGroups(): void;
    addGroup(start: number, count: number, materialIndex: number): void;
    computeBoundingBox(): void;
    translate(x: number, y: number, z: number): void;
    setAttribute(name: string, attribute: BufferAttribute): void;
    computeVertexNormals(): void;
    clone(): BufferGeometry;
    rotateX(angle: number): this;
    rotateY(angle: number): this;
    scale(x: number, y: number, z: number): this;
  }

  export class Shape {
    moveTo(x: number, y: number): void;
    lineTo(x: number, y: number): void;
    quadraticCurveTo(cpx: number, cpy: number, x: number, y: number): void;
  }

  export class ExtrudeGeometry extends BufferGeometry {
    constructor(shape: Shape, options?: object);
  }

  export class PlaneGeometry extends BufferGeometry {
    constructor(width?: number, height?: number);
  }

  export const FrontSide: number;
  export const DoubleSide: number;
  export const LinearFilter: number;
  export const LinearMipmapLinearFilter: number;

  export class Texture {
    colorSpace: string;
    needsUpdate: boolean;
    magFilter: number;
    minFilter: number;
    generateMipmaps: boolean;
    anisotropy: number;
    constructor(image?: CanvasImageSource);
    dispose(): void;
  }

  export class Color {
    constructor(color?: string | number);
    set(color: string | number): this;
  }

  export class Material {
    dispose(): void;
  }

  export class MeshStandardMaterial extends Material {
    map: Texture | null;
    color: Color;
    needsUpdate: boolean;
    constructor(parameters?: object);
  }

  export class MeshBasicMaterial extends Material {
    constructor(parameters?: object);
  }

  export class Object3D {
    position: Vector3;
    add(object: Object3D): this;
    removeFromParent(): this;
    traverse(callback: (object: Object3D) => void): void;
  }

  export class Mesh extends Object3D {
    material: Material | Material[];
    constructor(geometry?: BufferGeometry, material?: Material | Material[]);
  }

  export class Scene extends Object3D {
    background: Color | null;
  }

  export class PerspectiveCamera extends Object3D {
    fov: number;
    aspect: number;
    near: number;
    far: number;
    position: Vector3;
    constructor(fov?: number, aspect?: number, near?: number, far?: number);
    updateProjectionMatrix(): void;
    lookAt(target: Vector3): void;
    lookAt(x: number, y: number, z: number): void;
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
    constructor(parameters?: { antialias?: boolean; alpha?: boolean; preserveDrawingBuffer?: boolean });
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
