// Simple 3D equipment models built from primitives, mirroring the 2D drawings in
// features/assembly/drawings.tsx. Parts are keyed by the backend `visualization_id`.
// Units are roughly metres; y is up, z points toward the viewer.

export type Vec3 = [number, number, number];

/** `color` and `opacity` apply to structure shapes only; parts are colored by their condition. */
interface Look {
  color?: string;
  opacity?: number;
}

export type Prim =
  | ({ kind: "box"; size: Vec3; pos: Vec3; rot?: Vec3 } & Look)
  | ({ kind: "cyl"; r: number; rTop?: number; h: number; pos: Vec3; rot?: Vec3 } & Look)
  | ({ kind: "ring"; r: number; tube: number; pos: Vec3; rot?: Vec3 } & Look);

export interface Model3D {
  structure: Prim[];
  /** Outline-only shapes (cabinet or enclosure) drawn as faint lines so the inside stays visible. */
  frames?: Prim[];
  parts: Record<string, Prim[]>;
  camera: Vec3;
  target: Vec3;
}

const H = Math.PI / 2;

const DARK = "#30343b";
const FACE = "#4a5058";
const range = (n: number) => Array.from({ length: n }, (_, i) => i);

/**
 * Mainframe / 42U server rack with a rear-door coolant heat exchanger (like an IBM Z-class cabinet).
 * Front is +z; the default view looks at the rear, where the fans and coolant parts are. The doors and side panels are see-through.
 */
const rack: Model3D = {
  camera: [2.6, 2.3, -3.0],
  target: [0, 1.0, -0.2],
  structure: [
    { kind: "box", size: [0.58, 0.24, 0.2], pos: [0, 1.55, -0.46], color: "#3c4148", opacity: 0.22 }, // rear fan tray housing
    { kind: "box", size: [2.8, 0.05, 2.4], pos: [0, -0.025, 0], color: "#d3cec3" }, // raised floor
    { kind: "box", size: [0.7, 0.06, 1.2], pos: [0, 0.03, 0.02], color: DARK }, // base plinth
    ...[-0.29, 0.29].flatMap((x) =>
      [-0.5, 0.5].map((z): Prim => ({ kind: "box", size: [0.04, 2.0, 0.04], pos: [x, 1.03, z], color: DARK })),
    ), // four uprights
    { kind: "box", size: [0.64, 0.04, 1.06], pos: [0, 2.05, 0], color: DARK }, // roof
    { kind: "box", size: [0.02, 2.0, 1.04], pos: [-0.31, 1.03, 0], color: DARK, opacity: 0.14 }, // side panels
    { kind: "box", size: [0.02, 2.0, 1.04], pos: [0.31, 1.03, 0], color: DARK, opacity: 0.14 },
    { kind: "box", size: [0.62, 1.98, 0.02], pos: [0, 1.03, 0.54], color: DARK, opacity: 0.16 }, // front door
    ...range(10).map((i): Prim => ({ kind: "box", size: [0.5, 0.075, 0.8], pos: [0, 0.62 + i * 0.1, 0.02], color: DARK })), // servers
    ...range(10).map((i): Prim => ({ kind: "box", size: [0.5, 0.05, 0.012], pos: [0, 0.62 + i * 0.1, 0.43], color: FACE })), // server faces
    { kind: "box", size: [0.52, 0.34, 0.8], pos: [0, 1.82, 0.02], color: "#383d45" }, // processor drawer
    { kind: "box", size: [0.62, 1.9, 0.08], pos: [0, 1.0, -0.58], color: "#9aa0a6", opacity: 0.4 }, // rear-door heat exchanger
    ...range(12).map((i): Prim => ({ kind: "box", size: [0.56, 0.012, 0.09], pos: [0, 0.2 + i * 0.15, -0.58], color: "#6f757c" })), // coil fins
    { kind: "cyl", r: 0.018, h: 1.7, pos: [0.2, 1.0, -0.66], color: "#6f757c" }, // coolant supply pipe
    { kind: "cyl", r: 0.018, h: 1.7, pos: [0.27, 1.0, -0.66], color: "#6f757c" }, // coolant return pipe
  ],
  frames: [{ kind: "box", size: [0.7, 2.08, 1.3], pos: [0, 1.04, -0.04] }],
  parts: {
    "rack-air-filter": [{ kind: "box", size: [0.54, 0.3, 0.03], pos: [0, 0.3, 0.5] }],
    "rack-fan-impeller": [-0.17, 0, 0.17].map((x): Prim => ({ kind: "cyl", r: 0.085, h: 0.03, pos: [x, 1.55, -0.5], rot: [H, 0, 0] })),
    "rack-fan-motor": [-0.17, 0, 0.17].map((x): Prim => ({ kind: "cyl", r: 0.032, h: 0.08, pos: [x, 1.55, -0.45], rot: [H, 0, 0] })),
    "rack-fan-bearing": [-0.17, 0, 0.17].map((x): Prim => ({ kind: "ring", r: 0.045, tube: 0.011, pos: [x, 1.55, -0.4] })),
    "rack-coolant-valve": [
      { kind: "cyl", r: 0.05, h: 0.13, pos: [0.2, 0.55, -0.66] },
      { kind: "box", size: [0.1, 0.08, 0.1], pos: [0.2, 0.67, -0.66] },
    ],
    "rack-coolant-pump": [{ kind: "box", size: [0.2, 0.18, 0.2], pos: [-0.26, 0.2, -0.68] }],
    "rack-coolant-reservoir": [{ kind: "cyl", r: 0.07, h: 0.3, pos: [-0.26, 1.3, -0.68] }],
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

export const MODELS: Record<string, Model3D> = { rack, chiller };
