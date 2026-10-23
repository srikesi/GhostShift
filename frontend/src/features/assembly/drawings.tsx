import type { ReactNode } from "react";

// Technical schematic drawings. Each component part is keyed by the backend
// `Component.visualization_id`, so incidents can highlight parts from API data.
// To add a machine: add a Drawing with `structure` + `parts` keyed by visualization ids.

export interface PartShape {
  anchor: [number, number];
  /** Top-left of the label box shown when this part is the affected component. */
  callout: [number, number];
  shape: ReactNode;
}

export interface Drawing {
  viewBox: string;
  structure: ReactNode;
  parts: Record<string, PartShape>;
}

const range = (n: number) => Array.from({ length: n }, (_, i) => i);

const vmc: Drawing = {
  viewBox: "0 0 420 320",
  structure: (
    <>
      <line x1="14" y1="300" x2="406" y2="300" className="ground" />
      <rect x="40" y="252" width="330" height="46" rx="3" className="body" />
      <rect x="236" y="48" width="96" height="204" rx="2" className="body" />
      {range(5).map((i) => (
        <line key={i} x1="248" x2="320" y1={70 + i * 34} y2={70 + i * 34} className="detail" />
      ))}
      <rect x="126" y="64" width="126" height="58" rx="3" className="body" />
      <rect x="162" y="122" width="56" height="58" className="body" />
      <path d="M170 180h40l-4 8h-32z" className="body" />
      <path d="M176 188h28l-6 8h-16z" className="body" />
      <rect x="186" y="196" width="8" height="5" className="steel" />
      <rect x="136" y="201" width="108" height="13" rx="1" className="work" />
      <rect x="70" y="214" width="210" height="14" rx="2" className="body" />
      {range(6).map((i) => (
        <line key={i} x1={86 + i * 34} x2={86 + i * 34} y1="216" y2="226" className="detail" />
      ))}
      <rect x="96" y="228" width="160" height="24" rx="2" className="body" />
    </>
  ),
  parts: {
    "vmc-spindle-motor": {
      anchor: [190, 43],
      callout: [4, 30],
      shape: (
        <>
          <rect x="160" y="20" width="60" height="44" rx="3" />
          {range(6).map((i) => (
            <line key={i} x1={167 + i * 9} x2={167 + i * 9} y1="25" y2="59" className="fin" />
          ))}
        </>
      ),
    },
    "vmc-spindle-rear-bearing": {
      anchor: [190, 131],
      callout: [4, 126],
      shape: (
        <>
          <rect x="157" y="126" width="66" height="11" rx="2" />
          {range(7).map((i) => (
            <circle key={i} cx={165 + i * 8.3} cy="131.5" r="2.2" className="ball" />
          ))}
        </>
      ),
    },
    "vmc-spindle-front-bearing": {
      anchor: [190, 168],
      callout: [4, 156],
      shape: (
        <>
          <rect x="154" y="161" width="72" height="14" rx="2" />
          {range(8).map((i) => (
            <circle key={i} cx={161 + i * 8.3} cy="168" r="2.6" className="ball" />
          ))}
        </>
      ),
    },
    "vmc-ball-screw-x": {
      anchor: [176, 240],
      callout: [4, 184],
      shape: (
        <>
          <rect x="84" y="236" width="184" height="8" rx="4" />
          {range(22).map((i) => (
            <line key={i} x1={88 + i * 8} x2={92 + i * 8} y1="237" y2="243" className="fin" />
          ))}
          <rect x="162" y="232" width="26" height="16" rx="2" />
        </>
      ),
    },
    "vmc-coolant-pump": {
      anchor: [323, 275],
      callout: [110, 262],
      shape: (
        <>
          <rect x="298" y="262" width="50" height="26" rx="2" />
          <circle cx="323" cy="275" r="8" />
          <line x1="323" y1="262" x2="323" y2="254" className="fin" />
        </>
      ),
    },
    "vmc-tool-changer": {
      anchor: [372, 104],
      callout: [264, 6],
      shape: (
        <>
          <line x1="332" y1="104" x2="340" y2="104" className="fin" />
          <circle cx="372" cy="104" r="32" />
          {range(10).map((i) => {
            const a = (i / 10) * Math.PI * 2;
            return <circle key={i} cx={372 + Math.cos(a) * 24} cy={104 + Math.sin(a) * 24} r="4" className="ball" />;
          })}
          <circle cx="372" cy="104" r="7" />
        </>
      ),
    },
    "vmc-way-lube": {
      anchor: [355, 196],
      callout: [184, 226],
      shape: (
        <>
          <rect x="340" y="176" width="30" height="42" rx="2" />
          <line x1="344" y1="190" x2="366" y2="190" className="fin" />
          <circle cx="355" cy="206" r="5" />
        </>
      ),
    },
  },
};

const compressor: Drawing = {
  viewBox: "0 0 420 320",
  structure: (
    <>
      <rect x="14" y="26" width="392" height="266" rx="4" className="enclosure" />
      <text x="24" y="20" className="drawing-label">
        PACKAGE ENCLOSURE · CUTAWAY
      </text>
      <rect x="22" y="268" width="376" height="16" rx="2" className="body" />
      <path d="M315 120V40h80" className="pipe air" markerEnd="url(#arrow)" />
      <text x="330" y="36" className="drawing-label">
        AIR TO HEADER
      </text>
      <path d="M344 236h34V130H232v-16" className="pipe oil" />
      <path d="M40 98H28v54h142v26" className="pipe oil" />
      <path d="M254 214h32" className="pipe air" />
      <path d="M150 215h12" className="steel-line" />
      <rect x="182" y="124" width="52" height="22" rx="11" className="body" />
      <text x="34" y="146" className="drawing-label">
        OIL CIRCUIT
      </text>
    </>
  ),
  parts: {
    "cmp-oil-cooler": {
      anchor: [138, 83],
      callout: [40, 27],
      shape: (
        <>
          <rect x="40" y="52" width="196" height="62" rx="3" />
          <rect x="40" y="52" width="12" height="62" rx="2" className="ball" />
          <rect x="224" y="52" width="12" height="62" rx="2" className="ball" />
          {range(28).map((i) => (
            <line key={i} x1={57 + i * 6} x2={57 + i * 6} y1="57" y2="109" className="fin" />
          ))}
        </>
      ),
    },
    "cmp-cooling-fan": {
      anchor: [362, 80],
      callout: [256, 124],
      shape: (
        <>
          <circle cx="362" cy="80" r="34" />
          {range(5).map((i) => (
            <path
              key={i}
              d="M362 80c4-10 14-18 22-20-2 9-10 18-22 20z"
              transform={`rotate(${i * 72} 362 80)`}
              className="ball"
            />
          ))}
          <circle cx="362" cy="80" r="6" />
        </>
      ),
    },
    "cmp-drive-motor": {
      anchor: [95, 215],
      callout: [20, 290],
      shape: (
        <>
          <rect x="40" y="176" width="110" height="78" rx="6" />
          {range(6).map((i) => (
            <line key={i} x1="48" x2="142" y1={186 + i * 11} y2={186 + i * 11} className="fin" />
          ))}
          <rect x="80" y="164" width="30" height="12" rx="1" />
        </>
      ),
    },
    "cmp-airend": {
      anchor: [208, 214],
      callout: [150, 290],
      shape: (
        <>
          <rect x="162" y="178" width="92" height="72" rx="8" />
          <ellipse cx="192" cy="214" rx="15" ry="27" className="ball" />
          <ellipse cx="225" cy="214" rx="13" ry="27" className="ball" />
          {range(4).map((i) => (
            <line key={i} x1="180" x2="204" y1={196 + i * 12} y2={204 + i * 12} className="fin" />
          ))}
        </>
      ),
    },
    "cmp-inlet-valve": {
      anchor: [208, 162],
      callout: [24, 118],
      shape: (
        <>
          <rect x="190" y="148" width="36" height="30" rx="3" />
          <line x1="198" y1="163" x2="218" y2="163" className="fin" />
        </>
      ),
    },
    "cmp-oil-separator": {
      anchor: [315, 190],
      callout: [254, 290],
      shape: (
        <>
          <rect x="286" y="120" width="58" height="140" rx="24" />
          <rect x="309" y="200" width="12" height="28" rx="3" className="ball" />
        </>
      ),
    },
  },
};

export const DRAWINGS: Record<string, Drawing> = { vmc, compressor };
