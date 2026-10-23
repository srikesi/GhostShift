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

/** Computer room air handler, front cutaway: return air in at the top, supply air down into the raised floor. */
const crah: Drawing = {
  viewBox: "0 0 420 320",
  structure: (
    <>
      <path d="M220 6v20" className="pipe air" markerEnd="url(#arrow)" />
      <text x="230" y="18" className="drawing-label">
        RETURN AIR
      </text>
      <rect x="150" y="30" width="140" height="236" rx="3" className="body" />
      <path d="M162 84l58 58 58-58" className="coil" />
      <path d="M170 84l50 50 50-50" className="coil" />
      <text x="244" y="140" className="drawing-label">
        CW COIL
      </text>
      <path d="M290 112h46M290 138h46" className="pipe water" />
      <text x="342" y="116" className="drawing-label">
        CHW IN
      </text>
      <text x="342" y="142" className="drawing-label">
        CHW OUT
      </text>
      <line x1="205" y1="166" x2="205" y2="214" className="steel-line" />
      <line x1="40" y1="266" x2="380" y2="266" className="ground" />
      {range(9).map((i) => (
        <line key={i} x1={40 + i * 42.5} x2={40 + i * 42.5} y1="266" y2="272" className="detail" />
      ))}
      <path d="M205 268v26" className="pipe air" markerEnd="url(#arrow)" />
      <text x="214" y="290" className="drawing-label">
        SUPPLY AIR TO RAISED FLOOR
      </text>
    </>
  ),
  parts: {
    "crah-air-filter": {
      anchor: [220, 54],
      callout: [2, 44],
      shape: (
        <>
          <rect x="160" y="42" width="120" height="22" rx="2" />
          <path d={`M162 53${range(12).map((i) => `l5 ${i % 2 ? 9 : -9}`).join("")}`} className="fin" />
        </>
      ),
    },
    "crah-chw-valve": {
      anchor: [312, 112],
      callout: [2, 98],
      shape: (
        <>
          <path d="M302 104l20 16v-16l-20 16z" />
          <rect x="305" y="90" width="14" height="10" rx="1" />
        </>
      ),
    },
    "crah-humidifier": {
      anchor: [263, 186],
      callout: [2, 150],
      shape: (
        <>
          <rect x="245" y="166" width="36" height="42" rx="3" />
          <path d="M256 176c4 4-4 8 0 12M268 176c4 4-4 8 0 12" className="fin" />
        </>
      ),
    },
    "crah-condensate-pump": {
      anchor: [175, 244],
      callout: [2, 228],
      shape: (
        <>
          <rect x="160" y="236" width="30" height="20" rx="2" />
          <circle cx="175" cy="246" r="5" className="ball" />
        </>
      ),
    },
    "crah-fan-motor": {
      anchor: [205, 190],
      callout: [2, 176],
      shape: (
        <>
          <rect x="188" y="178" width="34" height="24" rx="3" />
          {range(3).map((i) => (
            <line key={i} x1="192" x2="218" y1={184 + i * 6} y2={184 + i * 6} className="fin" />
          ))}
        </>
      ),
    },
    "crah-fan-bearing": {
      anchor: [205, 206],
      callout: [2, 192],
      shape: (
        <>
          <rect x="192" y="170" width="26" height="7" rx="2" />
          <rect x="192" y="203" width="26" height="7" rx="2" />
          {range(4).map((i) => (
            <circle key={i} cx={196 + i * 6} cy="206.5" r="1.8" className="ball" />
          ))}
        </>
      ),
    },
    "crah-fan-impeller": {
      anchor: [205, 228],
      callout: [2, 212],
      shape: (
        <>
          <path d="M180 214h50l10 26h-70z" />
          {range(6).map((i) => (
            <line key={i} x1={184 + i * 8.5} x2={178 + i * 11} y1="216" y2="238" className="fin" />
          ))}
        </>
      ),
    },
  },
};

/** Air-cooled screw chiller, side view. */
const chiller: Drawing = {
  viewBox: "0 0 420 320",
  structure: (
    <>
      <rect x="14" y="40" width="392" height="230" rx="4" className="enclosure" />
      <rect x="14" y="270" width="392" height="14" rx="2" className="body" />
      <rect x="30" y="56" width="300" height="40" rx="2" className="body" />
      {range(24).map((i) => (
        <line key={i} x1={38 + i * 12} x2={38 + i * 12} y1="60" y2="92" className="detail" />
      ))}
      <text x="40" y="108" className="drawing-label">
        CONDENSER COIL
      </text>
      <path d="M240 196h20v-32" className="pipe air" />
      <path d="M310 120V96" className="pipe air" />
      <path d="M370 142h25V96" className="pipe oil" />
      <path d="M344 96v14H245v58" className="pipe oil" />
      <text x="252" y="186" className="drawing-label">
        OIL
      </text>
      <path d="M370 251h26" className="pipe water" markerEnd="url(#arrow)" />
      <text x="40" y="296" className="drawing-label">
        CHILLED WATER TO DATA HALLS
      </text>
    </>
  ),
  parts: {
    "ch-condenser-fans": {
      anchor: [180, 40],
      callout: [14, 4],
      shape: (
        <>
          {[80, 180, 280].map((x) => (
            <g key={x}>
              <ellipse cx={x} cy="44" rx="40" ry="9" />
              <rect x={x - 8} y="30" width="16" height="10" rx="2" className="ball" />
            </g>
          ))}
        </>
      ),
    },
    "ch-oil-cooler": {
      anchor: [366, 76],
      callout: [258, 4],
      shape: (
        <>
          <rect x="338" y="56" width="56" height="40" rx="2" />
          {range(8).map((i) => (
            <line key={i} x1={344 + i * 6.5} x2={344 + i * 6.5} y1="60" y2="92" className="fin" />
          ))}
        </>
      ),
    },
    "ch-oil-separator": {
      anchor: [310, 142],
      callout: [258, 292],
      shape: (
        <>
          <rect x="250" y="120" width="120" height="44" rx="22" />
          <rect x="300" y="134" width="20" height="16" rx="3" className="ball" />
        </>
      ),
    },
    "ch-compressor": {
      anchor: [195, 200],
      callout: [130, 292],
      shape: (
        <>
          <rect x="150" y="170" width="90" height="60" rx="8" />
          <ellipse cx="180" cy="200" rx="14" ry="22" className="ball" />
          <ellipse cx="212" cy="200" rx="12" ry="22" className="ball" />
        </>
      ),
    },
    "ch-compressor-motor": {
      anchor: [103, 201],
      callout: [14, 292],
      shape: (
        <>
          <rect x="60" y="176" width="86" height="50" rx="6" />
          {range(5).map((i) => (
            <line key={i} x1="66" x2="140" y1={184 + i * 8} y2={184 + i * 8} className="fin" />
          ))}
        </>
      ),
    },
    "ch-evaporator": {
      anchor: [205, 251],
      callout: [258, 292],
      shape: (
        <>
          <rect x="40" y="238" width="330" height="26" rx="13" />
          {[90, 320].map((x) => (
            <rect key={x} x={x} y="232" width="10" height="6" className="ball" />
          ))}
        </>
      ),
    },
  },
};

export const DRAWINGS: Record<string, Drawing> = { crah, chiller };
