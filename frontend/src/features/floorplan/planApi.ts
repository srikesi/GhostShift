import { request } from "../../api/client";

export interface PlanUnit {
  id: string;
  label: string;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
  photo: string | null;
  machine_id: string | null;
}

export interface FloorPlanData {
  site: string;
  width: number;
  height: number;
  zones: { id: string; label: string; x: number; y: number; w: number; h: number }[];
  labels: { text: string; x: number; y: number }[];
  units: PlanUnit[];
  links: { a: string; b: string; label: string }[];
  decor: {
    aisles: { kind: string; x: number; y: number; w: number; h: number; label: string }[];
    doors: { x: number; y: number; w: number; h: number; label: string; side: string }[];
    pipes: { points: [number, number][]; label: string; lx: number; ly: number }[];
    columns: [number, number][];
    scale: { x: number; y: number; metres: number; px: number } | null;
    north: { x: number; y: number } | null;
  };
}

export const getFloorPlan = () => request<FloorPlanData>("/api/floorplan");
