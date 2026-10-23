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

/** Mainframe / server rack, side cutaway: cold air in at the front, hot air through the rear-door coolant heat exchanger. */
const rack: Drawing = {
  viewBox: "0 0 480 320",
  structure: (
    <>
      <path d="M96 150h56" className="pipe air" markerEnd="url(#arrow)" />
      <text x="40" y="142" className="drawing-label">
        COLD AISLE AIR
      </text>
      <rect x="168" y="38" width="128" height="244" rx="3" className="body" />
      <rect x="160" y="38" width="8" height="244" rx="2" className="enclosure" />
      {range(10).map((i) => (
        <line key={i} x1="162" x2="166" y1={52 + i * 24} y2={52 + i * 24} className="detail" />
      ))}
      <rect x="180" y="44" width="108" height="40" rx="3" className="enclosure" />
      <text x="184" y="95" className="drawing-label">
        REAR FAN TRAY
      </text>
      <rect x="184" y="100" width="100" height="26" rx="3" className="body" />
      <text x="190" y="117" className="drawing-label">
        PROCESSOR DRAWER
      </text>
      {range(7).map((i) => (
        <g key={i}>
          <rect x="184" y={134 + i * 20} width="100" height="14" rx="2" className="body" />
          <circle cx="191" cy={141 + i * 20} r="1.8" className="ball" />
          <line x1="200" x2="276" y1={141 + i * 20} y2={141 + i * 20} className="detail" />
        </g>
      ))}
      <rect x="296" y="38" width="10" height="244" rx="2" className="enclosure" />
      {range(11).map((i) => (
        <line key={i} x1="296" x2="306" y1={46 + i * 22} y2={58 + i * 22} className="detail" />
      ))}
      <text x="298" y="304" className="drawing-label">
        REAR-DOOR HEAT EXCHANGER
      </text>
      <path d="M306 112h20M306 247h18M339 136v44M339 198v38" className="pipe water" />
      <line x1="120" y1="282" x2="440" y2="282" className="ground" />
      {range(9).map((i) => (
        <line key={i} x1={120 + i * 40} x2={120 + i * 40} y1="282" y2="288" className="detail" />
      ))}
      <text x="176" y="30" className="drawing-label">
        AIR FLOWS FRONT TO REAR
      </text>
    </>
  ),
  parts: {
    "rack-air-filter": {
      anchor: [174, 220],
      callout: [2, 208],
      shape: (
        <>
          <rect x="169" y="170" width="9" height="100" rx="1" />
          {range(11).map((i) => (
            <line key={i} x1="171" x2="177" y1={176 + i * 8.5} y2={176 + i * 8.5} className="fin" />
          ))}
        </>
      ),
    },
    "rack-fan-impeller": {
      anchor: [200, 64],
      callout: [2, 38],
      shape: (
        <>
          <rect x="188" y="50" width="24" height="28" rx="2" />
          {range(5).map((i) => (
            <line key={i} x1="190" x2="210" y1={54 + i * 5} y2={57 + i * 5} className="fin" />
          ))}
        </>
      ),
    },
    "rack-fan-motor": {
      anchor: [236, 64],
      callout: [2, 38],
      shape: (
        <>
          <rect x="222" y="52" width="28" height="24" rx="4" />
          {range(3).map((i) => (
            <line key={i} x1="226" x2="246" y1={58 + i * 6} y2={58 + i * 6} className="fin" />
          ))}
        </>
      ),
    },
    "rack-fan-bearing": {
      anchor: [270, 64],
      callout: [2, 38],
      shape: (
        <>
          <rect x="256" y="48" width="24" height="6" rx="2" />
          <rect x="256" y="74" width="24" height="6" rx="2" />
          {range(4).map((i) => (
            <circle key={i} cx={260 + i * 5.5} cy="77" r="1.5" className="ball" />
          ))}
        </>
      ),
    },
    "rack-coolant-valve": {
      anchor: [339, 188],
      callout: [332, 214],
      shape: (
        <>
          <path d="M327 180l24 16v-16l-24 16z" />
          <rect x="333" y="166" width="12" height="10" rx="1" />
        </>
      ),
    },
    "rack-coolant-pump": {
      anchor: [339, 247],
      callout: [332, 270],
      shape: (
        <>
          <rect x="324" y="236" width="30" height="22" rx="3" />
          <circle cx="339" cy="247" r="5" className="ball" />
        </>
      ),
    },
    "rack-coolant-reservoir": {
      anchor: [339, 114],
      callout: [332, 66],
      shape: (
        <>
          <rect x="326" y="92" width="26" height="44" rx="4" />
          <path d="M328 110h22" className="fin" />
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

export const DRAWINGS: Record<string, Drawing> = { rack, chiller };
