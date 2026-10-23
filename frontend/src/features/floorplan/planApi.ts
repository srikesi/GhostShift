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
}

export const getFloorPlan = () => request<FloorPlanData>("/api/floorplan");
