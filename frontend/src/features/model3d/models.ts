// Simple 3D equipment models built from primitives, mirroring the 2D drawings in
// features/assembly/drawings.tsx. Parts are keyed by the backend `visualization_id`.
// Units are roughly metres; y is up, z points toward the viewer.

export type Vec3 = [number, number, number];

export type Prim =
  | { kind: "box"; size: Vec3; pos: Vec3; rot?: Vec3 }
  | { kind: "cyl"; r: number; rTop?: number; h: number; pos: Vec3; rot?: Vec3 }
  | { kind: "ring"; r: number; tube: number; pos: Vec3; rot?: Vec3 };

export interface Model3D {
  structure: Prim[];
  /** Outline-only shapes (cabinet or enclosure) drawn as faint lines so the inside stays visible. */
  frames?: Prim[];
  parts: Record<string, Prim[]>;
  camera: Vec3;
  target: Vec3;
}

const H = Math.PI / 2;

/** Downflow CRAH: filters on top, A-frame chilled-water coil, EC supply fan at the bottom. */
const crah: Model3D = {
  camera: [2.9, 2.3, 3.6],
  target: [0.1, 1.05, 0],
  structure: [
    { kind: "box", size: [3.2, 0.06, 2.2], pos: [0, -0.03, 0] }, // raised floor
    { kind: "box", size: [1.4, 0.08, 0.9], pos: [0, 0.04, 0] }, // plinth
    { kind: "box", size: [1.4, 2.3, 0.04], pos: [0, 1.15, -0.45] }, // back panel
    { kind: "box", size: [0.66, 0.05, 0.8], pos: [-0.27, 1.45, 0], rot: [0, 0, 0.6] }, // coil, left slab
    { kind: "box", size: [0.66, 0.05, 0.8], pos: [0.27, 1.45, 0], rot: [0, 0, -0.6] }, // coil, right slab
    { kind: "cyl", r: 0.04, h: 0.6, pos: [0.98, 1.2, 0.22], rot: [0, 0, H] }, // chilled water in
    { kind: "cyl", r: 0.04, h: 0.6, pos: [0.98, 1.05, -0.12], rot: [0, 0, H] }, // chilled water out
    { kind: "cyl", r: 0.03, h: 0.5, pos: [0, 0.5, 0] }, // fan shaft
  ],
  frames: [{ kind: "box", size: [1.4, 2.3, 0.9], pos: [0, 1.15, 0] }],
  parts: {
    "crah-air-filter": [{ kind: "box", size: [1.3, 0.12, 0.8], pos: [0, 2.12, 0] }],
    "crah-chw-valve": [
      { kind: "cyl", r: 0.08, h: 0.2, pos: [1.0, 1.2, 0.22] },
      { kind: "box", size: [0.14, 0.12, 0.14], pos: [1.0, 1.37, 0.22] },
    ],
    "crah-fan-motor": [{ kind: "cyl", r: 0.16, h: 0.24, pos: [0, 0.64, 0] }],
    "crah-fan-bearing": [
      { kind: "ring", r: 0.17, tube: 0.035, pos: [0, 0.79, 0], rot: [H, 0, 0] },
      { kind: "ring", r: 0.17, tube: 0.035, pos: [0, 0.49, 0], rot: [H, 0, 0] },
    ],
    "crah-fan-impeller": [{ kind: "cyl", r: 0.45, rTop: 0.3, h: 0.2, pos: [0, 0.3, 0] }],
    "crah-humidifier": [{ kind: "box", size: [0.28, 0.36, 0.28], pos: [0.48, 0.92, -0.2] }],
    "crah-condensate-pump": [{ kind: "box", size: [0.22, 0.16, 0.22], pos: [-0.48, 0.16, 0.2] }],
  },
};

/** Air-cooled screw chiller: fans and coils on top, compressor train and vessels below. */
const chiller: Model3D = {
  camera: [4.2, 3.0, 4.6],
  target: [0, 0.95, 0],
  structure: [
    { kind: "box", size: [4.2, 0.12, 1.6], pos: [0, 0.06, 0] }, // skid
    { kind: "box", size: [3.0, 0.8, 0.05], pos: [-0.45, 1.5, 0.45], rot: [0.4, 0, 0] }, // condenser coil, front
    { kind: "box", size: [3.0, 0.8, 0.05], pos: [-0.45, 1.5, -0.45], rot: [-0.4, 0, 0] }, // condenser coil, back
    { kind: "cyl", r: 0.05, h: 0.6, pos: [0.75, 0.75, 0.1], rot: [0, 0, H] }, // discharge pipe
  ],
  frames: [{ kind: "box", size: [4.2, 2.0, 1.6], pos: [0, 1.06, 0] }],
  parts: {
    "ch-condenser-fans": [-1.4, -0.4, 0.6].map((x) => ({ kind: "cyl", r: 0.38, h: 0.12, pos: [x, 2.0, 0] }) as Prim),
    "ch-oil-cooler": [{ kind: "box", size: [0.7, 0.6, 0.06], pos: [1.5, 1.5, 0.45], rot: [0.4, 0, 0] }],
    "ch-compressor": [{ kind: "box", size: [0.8, 0.55, 0.55], pos: [0.1, 0.55, 0.1] }],
    "ch-compressor-motor": [{ kind: "cyl", r: 0.28, h: 0.7, pos: [-0.7, 0.55, 0.1], rot: [0, 0, H] }],
    "ch-oil-separator": [{ kind: "cyl", r: 0.25, h: 1.0, pos: [1.35, 0.75, 0.1], rot: [0, 0, H] }],
    "ch-evaporator": [{ kind: "cyl", r: 0.24, h: 2.8, pos: [0, 0.38, -0.5], rot: [0, 0, H] }],
  },
};

export const MODELS: Record<string, Model3D> = { crah, chiller };
